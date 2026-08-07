"""Offline unit tests for secret-safe rendering, duplicate/idempotent
behavior, and no-partial-profile guarantees (Candidate 02 Sections 21-22,
plus Implementation 02 Correction 3: `CredentialSourceReference` must not
expose `source_name` through `repr()`/`str()`, directly or nested inside
a containing object).

No test in this file ever constructs a value that resembles a usable API
key or private key. Only non-secret source names and state metadata are
used, matching the credential boundary in the controlling handoff.
"""

from __future__ import annotations

import unittest

from arb.venues.kalshi import (
    AuthorizationValue as AV,
    CredentialReferenceKind as CRK,
    CredentialReferenceState as CRS,
    CredentialSourceReference,
    HaltCode,
    NonSecretConfigurationInput as Input,
    RequestedCapability as RC,
    TaskAuthorizationCapabilityEnvelope as Envelope,
    TypedHalt,
    ValidatedDemoProfile,
    validate,
)

_DEMO_REST = "https://external-api.demo.kalshi.co/trade-api/v2"
_DEMO_WS = "wss://external-api-ws.demo.kalshi.co/trade-api/ws/v2"

_ACCEPTED_API_KEY_NAME = "KALSHI_DEMO_API_KEY_ID"
_ACCEPTED_PEM_NAME = "KALSHI_DEMO_PRIVATE_KEY_PEM"

# Obvious non-secret placeholder/sentinel tokens only. None of these
# resembles a usable key of any kind.
_NON_SECRET_PLACEHOLDER_SOURCE_NAME = "<PRIVATE_KEY>"
_UNIQUE_SENTINEL_SOURCE_NAME = "SENTINEL_TOKEN_ZQX9981_NEVER_RENDERED"


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
        demo_authenticated_reads=AV.PERMITTED,
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


class CredentialSourceReferenceRenderingTests(unittest.TestCase):
    """Correction 3 regression coverage."""

    def test_direct_repr_omits_source_name_for_accepted_api_key_name(self) -> None:
        ref = CredentialSourceReference(
            CRK.API_KEY_ID_ENV_SOURCE, _ACCEPTED_API_KEY_NAME, CRS.CONFIGURED
        )
        self.assertNotIn(_ACCEPTED_API_KEY_NAME, repr(ref))

    def test_direct_repr_omits_source_name_for_accepted_pem_name(self) -> None:
        ref = CredentialSourceReference(
            CRK.PRIVATE_KEY_PEM_ENV_SOURCE, _ACCEPTED_PEM_NAME, CRS.CONFIGURED
        )
        self.assertNotIn(_ACCEPTED_PEM_NAME, repr(ref))

    def test_direct_str_omits_source_name_for_accepted_api_key_name(self) -> None:
        ref = CredentialSourceReference(
            CRK.API_KEY_ID_ENV_SOURCE, _ACCEPTED_API_KEY_NAME, CRS.CONFIGURED
        )
        self.assertNotIn(_ACCEPTED_API_KEY_NAME, str(ref))

    def test_direct_str_omits_source_name_for_accepted_pem_name(self) -> None:
        ref = CredentialSourceReference(
            CRK.PRIVATE_KEY_PEM_ENV_SOURCE, _ACCEPTED_PEM_NAME, CRS.CONFIGURED
        )
        self.assertNotIn(_ACCEPTED_PEM_NAME, str(ref))

    def test_direct_repr_and_str_omit_unique_sentinel_source_name(self) -> None:
        ref = CredentialSourceReference(
            CRK.API_KEY_ID_ENV_SOURCE, _UNIQUE_SENTINEL_SOURCE_NAME, CRS.CONFIGURED
        )
        self.assertNotIn(_UNIQUE_SENTINEL_SOURCE_NAME, repr(ref))
        self.assertNotIn(_UNIQUE_SENTINEL_SOURCE_NAME, str(ref))

    def test_repr_exposes_only_kind_and_state(self) -> None:
        ref = CredentialSourceReference(
            CRK.API_KEY_ID_ENV_SOURCE, _UNIQUE_SENTINEL_SOURCE_NAME, CRS.CONFIGURED
        )
        rendered = repr(ref)
        self.assertIn("API_KEY_ID_ENV_SOURCE", rendered)
        self.assertIn("CONFIGURED", rendered)

    def test_containing_nonsecret_configuration_input_repr_omits_sentinel(self) -> None:
        references = (
            CredentialSourceReference(
                CRK.API_KEY_ID_ENV_SOURCE, _UNIQUE_SENTINEL_SOURCE_NAME, CRS.CONFIGURED
            ),
            CredentialSourceReference(
                CRK.PRIVATE_KEY_PEM_ENV_SOURCE, _ACCEPTED_PEM_NAME, CRS.CONFIGURED
            ),
        )
        cfg = _config(
            requested_capability=RC.DEMO_AUTHENTICATED_READ.value,
            capability_envelope=_envelope(
                demo_authenticated_reads=AV.PERMITTED, credential_use=AV.PERMITTED
            ),
            credential_references=references,
        )
        rendered = repr(cfg)
        self.assertNotIn(_UNIQUE_SENTINEL_SOURCE_NAME, rendered)
        self.assertNotIn(_ACCEPTED_PEM_NAME, rendered)

    def test_containing_nonsecret_configuration_input_str_omits_sentinel(self) -> None:
        references = (
            CredentialSourceReference(
                CRK.API_KEY_ID_ENV_SOURCE, _UNIQUE_SENTINEL_SOURCE_NAME, CRS.CONFIGURED
            ),
            CredentialSourceReference(
                CRK.PRIVATE_KEY_PEM_ENV_SOURCE, _ACCEPTED_PEM_NAME, CRS.CONFIGURED
            ),
        )
        cfg = _config(
            requested_capability=RC.DEMO_AUTHENTICATED_READ.value,
            capability_envelope=_envelope(
                demo_authenticated_reads=AV.PERMITTED, credential_use=AV.PERMITTED
            ),
            credential_references=references,
        )
        rendered = str(cfg)
        self.assertNotIn(_UNIQUE_SENTINEL_SOURCE_NAME, rendered)
        self.assertNotIn(_ACCEPTED_PEM_NAME, rendered)

    def test_equality_still_distinguishes_by_source_name(self) -> None:
        # Rendering is restricted, but equality (an internal, non-printed
        # comparison) still legitimately depends on source_name.
        a = CredentialSourceReference(
            CRK.API_KEY_ID_ENV_SOURCE, _ACCEPTED_API_KEY_NAME, CRS.CONFIGURED
        )
        b = CredentialSourceReference(
            CRK.API_KEY_ID_ENV_SOURCE, _UNIQUE_SENTINEL_SOURCE_NAME, CRS.CONFIGURED
        )
        self.assertNotEqual(a, b)


class SecretSafeRenderingTests(unittest.TestCase):
    def test_typed_halt_str_contains_no_placeholder_source_name(self) -> None:
        references = (
            CredentialSourceReference(
                CRK.API_KEY_ID_ENV_SOURCE,
                _NON_SECRET_PLACEHOLDER_SOURCE_NAME,
                CRS.CONFIGURED,
            ),
            CredentialSourceReference(
                CRK.PRIVATE_KEY_PEM_ENV_SOURCE, _ACCEPTED_PEM_NAME, CRS.CONFIGURED
            ),
        )
        result = validate(
            _config(
                requested_capability=RC.DEMO_AUTHENTICATED_READ.value,
                capability_envelope=_envelope(
                    demo_authenticated_reads=AV.PERMITTED, credential_use=AV.PERMITTED
                ),
                credential_references=references,
            )
        )
        self.assertIsNotNone(result.halt)
        rendered = str(result.halt)
        self.assertNotIn(_NON_SECRET_PLACEHOLDER_SOURCE_NAME, rendered)
        self.assertNotIn("<PRIVATE_KEY>", rendered)

    def test_halt_rendering_omits_unique_sentinel_source_name(self) -> None:
        references = (
            CredentialSourceReference(
                CRK.API_KEY_ID_ENV_SOURCE,
                _UNIQUE_SENTINEL_SOURCE_NAME,
                CRS.CONFIGURED,
            ),
            CredentialSourceReference(
                CRK.PRIVATE_KEY_PEM_ENV_SOURCE, _ACCEPTED_PEM_NAME, CRS.CONFIGURED
            ),
        )
        result = validate(
            _config(
                requested_capability=RC.DEMO_AUTHENTICATED_READ.value,
                capability_envelope=_envelope(
                    demo_authenticated_reads=AV.PERMITTED, credential_use=AV.PERMITTED
                ),
                credential_references=references,
            )
        )
        self.assertIsNotNone(result.halt)
        self.assertNotIn(_UNIQUE_SENTINEL_SOURCE_NAME, str(result.halt))
        self.assertNotIn(_UNIQUE_SENTINEL_SOURCE_NAME, repr(result.halt))

    def test_typed_halt_repr_matches_str(self) -> None:
        result = validate(_config(environment="UNSET"))
        self.assertIsNotNone(result.halt)
        self.assertEqual(str(result.halt), repr(result.halt))

    def test_typed_halt_rendering_is_deterministic(self) -> None:
        result_a = validate(_config(environment="UNSET"))
        result_b = validate(_config(environment="UNSET"))
        self.assertEqual(str(result_a.halt), str(result_b.halt))

    def test_success_profile_repr_never_contains_source_names(self) -> None:
        references = (
            CredentialSourceReference(
                CRK.API_KEY_ID_ENV_SOURCE, _ACCEPTED_API_KEY_NAME, CRS.CONFIGURED
            ),
            CredentialSourceReference(
                CRK.PRIVATE_KEY_PEM_ENV_SOURCE, _ACCEPTED_PEM_NAME, CRS.CONFIGURED
            ),
        )
        result = validate(
            _config(
                requested_capability=RC.DEMO_AUTHENTICATED_READ.value,
                capability_envelope=_envelope(
                    demo_authenticated_reads=AV.PERMITTED, credential_use=AV.PERMITTED
                ),
                credential_references=references,
            )
        )
        self.assertIsNotNone(result.success)
        rendered = repr(result.success)
        # The profile stores only credential *kind* and *state*, never the
        # source name, so the accepted source-name strings must not appear.
        self.assertNotIn(_ACCEPTED_API_KEY_NAME, rendered)
        self.assertNotIn(_ACCEPTED_PEM_NAME, rendered)

    def test_success_profile_explicit_booleans(self) -> None:
        result = validate(_config())
        self.assertIsNotNone(result.success)
        self.assertFalse(result.success.secret_loaded)
        self.assertFalse(result.success.transport_constructed)
        self.assertFalse(result.success.network_request_sent)

    def test_validated_demo_profile_rejects_true_secret_loaded(self) -> None:
        with self.assertRaises(ValueError):
            ValidatedDemoProfile(
                environment=None,
                rest=None,
                websocket=None,
                requested_capability=None,
                effective_capability=None,
                credential_reference_states=(),
                allowlist_revision="r1",
                validation_schema_revision=1,
                secret_loaded=True,
            )


class IdempotencyAndRecoveryTests(unittest.TestCase):
    def test_identical_input_produces_byte_identical_semantic_result(self) -> None:
        result_a = validate(_config())
        result_b = validate(_config())
        self.assertEqual(result_a.success, result_b.success)

    def test_identical_halting_input_produces_identical_halt(self) -> None:
        result_a = validate(_config(environment="KALSHI_PRODUCTION"))
        result_b = validate(_config(environment="KALSHI_PRODUCTION"))
        self.assertEqual(result_a.halt, result_b.halt)

    def test_conflicting_duplicate_input_rejects(self) -> None:
        references = (
            CredentialSourceReference(
                CRK.API_KEY_ID_ENV_SOURCE, _ACCEPTED_API_KEY_NAME, CRS.CONFIGURED
            ),
            CredentialSourceReference(
                CRK.API_KEY_ID_ENV_SOURCE, _ACCEPTED_API_KEY_NAME, CRS.CONFIGURED
            ),
        )
        result = validate(_config(credential_references=references))
        self.assertIsNone(result.success)
        self.assertEqual(result.halt.code, HaltCode.CONFIGURATION_AMBIGUOUS)

    def test_malformed_input_never_returns_partial_profile(self) -> None:
        result = validate(_config(rest_endpoint=""))
        self.assertIsNone(result.success)
        self.assertIsNotNone(result.halt)

    def test_halted_result_cannot_be_mutated_into_success(self) -> None:
        result = validate(_config(environment="UNSET"))
        with self.assertRaises(Exception):
            result.success = "not-a-real-profile"  # type: ignore[misc]

    def test_corrected_input_requires_new_attempt(self) -> None:
        broken = validate(_config(environment="UNSET"))
        self.assertIsNone(broken.success)
        fixed = validate(_config(environment="KALSHI_DEMO"))
        self.assertIsNotNone(fixed.success)

    def test_validation_result_rejects_both_success_and_halt(self) -> None:
        from arb.venues.kalshi.models import ValidationResult, ValidationStage

        success = validate(_config()).success
        self.assertIsNotNone(success)
        real_halt = TypedHalt(
            code=HaltCode.ENVIRONMENT_UNSET, stage=ValidationStage.NON_SECRET_PARSED
        )
        with self.assertRaises(ValueError):
            ValidationResult(success=success, halt=real_halt)

    def test_validation_result_rejects_neither_success_nor_halt(self) -> None:
        from arb.venues.kalshi.models import ValidationResult

        with self.assertRaises(ValueError):
            ValidationResult()


if __name__ == "__main__":
    unittest.main()
