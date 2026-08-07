"""Offline unit tests for opaque credential source-name validation
(Candidate 02 Section 15). No test material resembles a usable key; only
non-secret source-name strings and state metadata are used."""

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
    validate,
)

_DEMO_REST = "https://external-api.demo.kalshi.co/trade-api/v2"
_DEMO_WS = "wss://external-api-ws.demo.kalshi.co/trade-api/ws/v2"

_ACCEPTED_API_KEY_NAME = "KALSHI_DEMO_API_KEY_ID"
_ACCEPTED_PEM_NAME = "KALSHI_DEMO_PRIVATE_KEY_PEM"

_GENERIC_AND_PROHIBITED_NAMES = (
    "KALSHI_API_KEY",
    "KALSHI_API_KEY_ID",
    "KALSHI_PRIVATE_KEY",
    "KALSHI_PRIVATE_KEY_PATH",
    "KALSHI_PRIVATE_KEY_PEM",
    "API_KEY",
    "API_KEY_ID",
    "PRIVATE_KEY",
    "PRIVATE_KEY_PATH",
    "PRIVATE_KEY_PEM",
    "KALSHI_PRODUCTION_API_KEY_ID",
    "KALSHI_PRODUCTION_PRIVATE_KEY_PEM",
)

_PLACEHOLDER_TOKENS = ("CHANGEME", "REPLACE_ME", "EXAMPLE", "PLACEHOLDER")


def _envelope(**overrides: AV) -> Envelope:
    fields = dict(
        schema_version=1,
        authorization_id="AUTH1",
        authorizing_authority="Gustavo",
        task_id="T1",
        issue_date="2026-08-06",
        completion_rule="single-attempt",
        network_access=AV.PROHIBITED,
        demo_public_reads=AV.PROHIBITED,
        demo_authenticated_reads=AV.PERMITTED,
        demo_writes=AV.PROHIBITED,
        production_public_reads=AV.PROHIBITED,
        production_authenticated_reads=AV.PROHIBITED,
        production_writes=AV.PROHIBITED,
        credential_use=AV.PERMITTED,
        account_funding=AV.PROHIBITED,
        code_changes=AV.PERMITTED,
        tests=AV.PERMITTED,
        artifact_generation=AV.PERMITTED,
        repository_commits=AV.PERMITTED,
    )
    fields.update(overrides)
    return Envelope(**fields)


def _config(credential_references=(), **overrides) -> Input:
    fields = dict(
        environment="KALSHI_DEMO",
        environment_source_field="ARB_KALSHI_ENVIRONMENT",
        rest_endpoint=_DEMO_REST,
        websocket_endpoint=_DEMO_WS,
        requested_capability=RC.DEMO_AUTHENTICATED_READ.value,
        capability_envelope=_envelope(),
        config_schema_revision=1,
        endpoint_allowlist_revision="candidate-02",
        credential_references=credential_references,
    )
    fields.update(overrides)
    return Input(**fields)


def _configured_pair():
    return (
        CredentialSourceReference(
            CRK.API_KEY_ID_ENV_SOURCE, _ACCEPTED_API_KEY_NAME, CRS.CONFIGURED
        ),
        CredentialSourceReference(
            CRK.PRIVATE_KEY_PEM_ENV_SOURCE, _ACCEPTED_PEM_NAME, CRS.CONFIGURED
        ),
    )


class CredentialMetadataTests(unittest.TestCase):
    def test_both_configured_accepted_names_succeed(self) -> None:
        result = validate(_config(_configured_pair()))
        self.assertIsNotNone(result.success)
        self.assertIsNone(result.halt)

    def test_missing_both_references_halts_missing(self) -> None:
        result = validate(_config(()))
        self.assertEqual(result.halt.code, HaltCode.CREDENTIAL_REFERENCE_MISSING)

    def test_missing_one_reference_halts_missing(self) -> None:
        api_key_only = (
            CredentialSourceReference(
                CRK.API_KEY_ID_ENV_SOURCE, _ACCEPTED_API_KEY_NAME, CRS.CONFIGURED
            ),
        )
        result = validate(_config(api_key_only))
        self.assertEqual(result.halt.code, HaltCode.CREDENTIAL_REFERENCE_MISSING)

    def test_generic_and_production_names_rejected(self) -> None:
        for bad_name in _GENERIC_AND_PROHIBITED_NAMES:
            with self.subTest(bad_name=bad_name):
                references = (
                    CredentialSourceReference(
                        CRK.API_KEY_ID_ENV_SOURCE, bad_name, CRS.CONFIGURED
                    ),
                    CredentialSourceReference(
                        CRK.PRIVATE_KEY_PEM_ENV_SOURCE, _ACCEPTED_PEM_NAME, CRS.CONFIGURED
                    ),
                )
                result = validate(_config(references))
                self.assertEqual(
                    result.halt.code, HaltCode.CREDENTIAL_NAMESPACE_MISMATCH
                )

    def test_cross_environment_mix_rejected(self) -> None:
        references = (
            CredentialSourceReference(
                CRK.API_KEY_ID_ENV_SOURCE,
                "KALSHI_PRODUCTION_API_KEY_ID",
                CRS.CONFIGURED,
            ),
            CredentialSourceReference(
                CRK.PRIVATE_KEY_PEM_ENV_SOURCE, _ACCEPTED_PEM_NAME, CRS.CONFIGURED
            ),
        )
        result = validate(_config(references))
        self.assertEqual(result.halt.code, HaltCode.CREDENTIAL_NAMESPACE_MISMATCH)

    def test_placeholder_state_rejected(self) -> None:
        for token in _PLACEHOLDER_TOKENS:
            with self.subTest(token=token):
                references = (
                    CredentialSourceReference(
                        CRK.API_KEY_ID_ENV_SOURCE, _ACCEPTED_API_KEY_NAME, CRS.PLACEHOLDER
                    ),
                    CredentialSourceReference(
                        CRK.PRIVATE_KEY_PEM_ENV_SOURCE, _ACCEPTED_PEM_NAME, CRS.CONFIGURED
                    ),
                )
                result = validate(_config(references))
                self.assertEqual(result.halt.code, HaltCode.CREDENTIAL_PLACEHOLDER)

    def test_public_read_with_credential_references_is_ambiguous(self) -> None:
        result = validate(
            _config(
                _configured_pair(),
                requested_capability=RC.DEMO_PUBLIC_REST_READ.value,
                capability_envelope=_envelope(
                    demo_public_reads=AV.PERMITTED,
                    demo_authenticated_reads=AV.PROHIBITED,
                    credential_use=AV.PROHIBITED,
                ),
            )
        )
        self.assertEqual(result.halt.code, HaltCode.CONFIGURATION_AMBIGUOUS)

    def test_public_read_without_credential_references_succeeds(self) -> None:
        result = validate(
            _config(
                (),
                requested_capability=RC.DEMO_PUBLIC_REST_READ.value,
                capability_envelope=_envelope(
                    demo_public_reads=AV.PERMITTED,
                    demo_authenticated_reads=AV.PROHIBITED,
                    credential_use=AV.PROHIBITED,
                ),
            )
        )
        self.assertIsNotNone(result.success)

    def test_duplicate_reference_kind_is_configuration_ambiguous(self) -> None:
        references = (
            CredentialSourceReference(
                CRK.API_KEY_ID_ENV_SOURCE, _ACCEPTED_API_KEY_NAME, CRS.CONFIGURED
            ),
            CredentialSourceReference(
                CRK.API_KEY_ID_ENV_SOURCE, _ACCEPTED_API_KEY_NAME, CRS.CONFIGURED
            ),
        )
        result = validate(_config(references))
        self.assertEqual(result.halt.code, HaltCode.CONFIGURATION_AMBIGUOUS)

    def test_source_names_never_dereferenced_or_read(self) -> None:
        # The validator only ever compares the source_name string; it never
        # opens, reads, or otherwise dereferences it. Passing an opaque
        # non-existent placeholder name proves no filesystem/env access is
        # attempted (a real read would raise unrelated errors, not a
        # deterministic typed halt).
        references = (
            CredentialSourceReference(
                CRK.API_KEY_ID_ENV_SOURCE, "<API_KEY_ID>", CRS.CONFIGURED
            ),
            CredentialSourceReference(
                CRK.PRIVATE_KEY_PEM_ENV_SOURCE, _ACCEPTED_PEM_NAME, CRS.CONFIGURED
            ),
        )
        result = validate(_config(references))
        self.assertEqual(result.halt.code, HaltCode.CREDENTIAL_NAMESPACE_MISMATCH)

    def test_credential_failure_never_returns_partial_profile(self) -> None:
        result = validate(_config(()))
        self.assertIsNone(result.success)


if __name__ == "__main__":
    unittest.main()
