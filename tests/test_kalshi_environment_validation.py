"""Offline unit tests for environment validation (Candidate 02 Section 13)."""

from __future__ import annotations

import unittest

from arb.venues.kalshi import (
    AuthorizationValue as AV,
    HaltCode,
    NonSecretConfigurationInput as Input,
    RequestedCapability as RC,
    TaskAuthorizationCapabilityEnvelope as Envelope,
    ValidationStage,
    validate,
)

_DEMO_REST = "https://external-api.demo.kalshi.co/trade-api/v2"
_DEMO_WS = "wss://external-api-ws.demo.kalshi.co/trade-api/ws/v2"


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


def _config(environment: str, **overrides) -> Input:
    fields = dict(
        environment=environment,
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


class EnvironmentValidationTests(unittest.TestCase):
    def test_missing_environment_halts_unset(self) -> None:
        result = validate(_config(""))
        self.assertIsNone(result.success)
        self.assertEqual(result.halt.code, HaltCode.ENVIRONMENT_UNSET)
        self.assertEqual(result.halt.stage, ValidationStage.NON_SECRET_PARSED)

    def test_none_environment_halts_unset(self) -> None:
        result = validate(_config(None))
        self.assertEqual(result.halt.code, HaltCode.ENVIRONMENT_UNSET)

    def test_explicit_unset_token_halts_unset(self) -> None:
        result = validate(_config("UNSET"))
        self.assertEqual(result.halt.code, HaltCode.ENVIRONMENT_UNSET)

    def test_whitespace_environment_halts_unknown(self) -> None:
        # A non-empty, non-"UNSET" token (even if it is only whitespace) is
        # not a recognized enum value, so it halts as unknown rather than
        # unset.
        result = validate(_config("   "))
        self.assertEqual(result.halt.code, HaltCode.ENVIRONMENT_UNKNOWN)

    def test_unknown_environment_token_halts_unknown(self) -> None:
        result = validate(_config("KALSHI_SANDBOX"))
        self.assertEqual(result.halt.code, HaltCode.ENVIRONMENT_UNKNOWN)

    def test_boolean_style_token_halts_unknown(self) -> None:
        result = validate(_config("true"))
        self.assertEqual(result.halt.code, HaltCode.ENVIRONMENT_UNKNOWN)

    def test_production_environment_halts_production_prohibited(self) -> None:
        result = validate(_config("KALSHI_PRODUCTION"))
        self.assertEqual(result.halt.code, HaltCode.PRODUCTION_ACCESS_PROHIBITED)

    def test_demo_environment_progresses_past_environment_validation(self) -> None:
        result = validate(_config("KALSHI_DEMO"))
        # Public-read success proves environment validation passed and the
        # pipeline continued.
        self.assertIsNotNone(result.success)
        self.assertIsNone(result.halt)
        self.assertEqual(result.success.environment.value, "KALSHI_DEMO")

    def test_no_environment_inference_from_endpoint_host(self) -> None:
        # A Demo-shaped endpoint must not cause environment inference: an
        # explicit UNSET environment still halts even though the endpoints
        # are exact Demo endpoints.
        result = validate(_config("UNSET"))
        self.assertEqual(result.halt.code, HaltCode.ENVIRONMENT_UNSET)

    def test_environment_failure_never_returns_partial_profile(self) -> None:
        result = validate(_config("KALSHI_PRODUCTION"))
        self.assertIsNone(result.success)


if __name__ == "__main__":
    unittest.main()
