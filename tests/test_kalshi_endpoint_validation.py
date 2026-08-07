"""Offline unit tests for endpoint validation (Candidate 02 Section 14)."""

from __future__ import annotations

import unittest

from arb.venues.kalshi import (
    AuthorizationValue as AV,
    HaltCode,
    NonSecretConfigurationInput as Input,
    RequestedCapability as RC,
    TaskAuthorizationCapabilityEnvelope as Envelope,
    validate,
)

_DEMO_REST = "https://external-api.demo.kalshi.co/trade-api/v2"
_DEMO_WS = "wss://external-api-ws.demo.kalshi.co/trade-api/ws/v2"
_PRODUCTION_REST = "https://external-api.kalshi.com/trade-api/v2"
_PRODUCTION_WS = "wss://external-api-ws.kalshi.com/trade-api/ws/v2"


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


def _config(rest: str, websocket: str, **overrides) -> Input:
    fields = dict(
        environment="KALSHI_DEMO",
        environment_source_field="ARB_KALSHI_ENVIRONMENT",
        rest_endpoint=rest,
        websocket_endpoint=websocket,
        requested_capability=RC.DEMO_PUBLIC_REST_READ.value,
        capability_envelope=_envelope(),
        config_schema_revision=1,
        endpoint_allowlist_revision="candidate-02",
    )
    fields.update(overrides)
    return Input(**fields)


def _rest_halt_code(rest_url: str) -> HaltCode:
    result = validate(_config(rest_url, _DEMO_WS))
    assert result.halt is not None, (rest_url, result.success)
    return result.halt.code


def _ws_halt_code(ws_url: str) -> HaltCode:
    result = validate(_config(_DEMO_REST, ws_url))
    assert result.halt is not None, (ws_url, result.success)
    return result.halt.code


class EndpointValidationTests(unittest.TestCase):
    def test_exact_demo_rest_and_websocket_succeed(self) -> None:
        result = validate(_config(_DEMO_REST, _DEMO_WS))
        self.assertIsNotNone(result.success)
        self.assertEqual(result.success.rest.host, "external-api.demo.kalshi.co")
        self.assertEqual(result.success.websocket.host, "external-api-ws.demo.kalshi.co")

    def test_omitted_and_explicit_443_canonicalize_identically(self) -> None:
        explicit = validate(
            _config(
                "https://external-api.demo.kalshi.co:443/trade-api/v2",
                "wss://external-api-ws.demo.kalshi.co:443/trade-api/ws/v2",
            )
        )
        omitted = validate(_config(_DEMO_REST, _DEMO_WS))
        self.assertIsNotNone(explicit.success)
        self.assertIsNotNone(omitted.success)
        self.assertEqual(explicit.success.rest, omitted.success.rest)
        self.assertEqual(explicit.success.websocket, omitted.success.websocket)

    def test_missing_rest_endpoint_halts(self) -> None:
        self.assertEqual(_rest_halt_code(""), HaltCode.ENDPOINT_MISSING)

    def test_missing_websocket_endpoint_halts(self) -> None:
        self.assertEqual(_ws_halt_code(""), HaltCode.ENDPOINT_MISSING)

    def test_production_rest_yields_environment_mismatch(self) -> None:
        self.assertEqual(
            _rest_halt_code(_PRODUCTION_REST), HaltCode.ENVIRONMENT_ENDPOINT_MISMATCH
        )

    def test_production_websocket_yields_environment_mismatch(self) -> None:
        self.assertEqual(
            _ws_halt_code(_PRODUCTION_WS), HaltCode.ENVIRONMENT_ENDPOINT_MISMATCH
        )

    def test_compatibility_host_rejected(self) -> None:
        self.assertEqual(
            _rest_halt_code("https://demo-api.kalshi.co/trade-api/v2"),
            HaltCode.ENDPOINT_HOST_PROHIBITED,
        )

    def test_legacy_elections_host_rejected(self) -> None:
        self.assertEqual(
            _rest_halt_code("https://api.elections.kalshi.com/trade-api/v2"),
            HaltCode.ENDPOINT_HOST_PROHIBITED,
        )

    def test_custom_host_rejected(self) -> None:
        self.assertEqual(
            _rest_halt_code("https://my-custom-proxy.example.com/trade-api/v2"),
            HaltCode.ENDPOINT_HOST_PROHIBITED,
        )

    def test_deceptive_subdomain_rejected(self) -> None:
        self.assertEqual(
            _rest_halt_code("https://external-api.demo.kalshi.co.evil.example/trade-api/v2"),
            HaltCode.ENDPOINT_HOST_PROHIBITED,
        )

    def test_substring_containing_host_rejected(self) -> None:
        self.assertEqual(
            _rest_halt_code("https://notexternal-api.demo.kalshi.co/trade-api/v2"),
            HaltCode.ENDPOINT_HOST_PROHIBITED,
        )

    def test_ip_literal_rejected(self) -> None:
        self.assertEqual(
            _rest_halt_code("https://93.184.216.34/trade-api/v2"),
            HaltCode.ENDPOINT_HOST_PROHIBITED,
        )

    def test_trailing_dot_host_rejected(self) -> None:
        self.assertEqual(
            _rest_halt_code("https://external-api.demo.kalshi.co./trade-api/v2"),
            HaltCode.ENDPOINT_HOST_PROHIBITED,
        )

    def test_punycode_host_rejected(self) -> None:
        self.assertEqual(
            _rest_halt_code("https://xn--external-api-demo-kalshi-co.example/trade-api/v2"),
            HaltCode.ENDPOINT_HOST_PROHIBITED,
        )

    def test_unicode_host_rejected(self) -> None:
        self.assertEqual(
            _rest_halt_code("https://exтernal-api.demo.kalshi.co/trade-api/v2"),
            HaltCode.ENDPOINT_HOST_PROHIBITED,
        )

    def test_user_info_rejected(self) -> None:
        self.assertEqual(
            _rest_halt_code("https://user:pass@external-api.demo.kalshi.co/trade-api/v2"),
            HaltCode.ENDPOINT_MALFORMED,
        )

    def test_query_rejected(self) -> None:
        self.assertEqual(
            _rest_halt_code("https://external-api.demo.kalshi.co/trade-api/v2?x=1"),
            HaltCode.ENDPOINT_MALFORMED,
        )

    def test_fragment_rejected(self) -> None:
        self.assertEqual(
            _rest_halt_code("https://external-api.demo.kalshi.co/trade-api/v2#frag"),
            HaltCode.ENDPOINT_MALFORMED,
        )

    def test_wrong_scheme_rejected(self) -> None:
        self.assertEqual(
            _rest_halt_code("http://external-api.demo.kalshi.co/trade-api/v2"),
            HaltCode.ENDPOINT_SCHEME_PROHIBITED,
        )

    def test_wrong_websocket_scheme_rejected(self) -> None:
        self.assertEqual(
            _ws_halt_code("ws://external-api-ws.demo.kalshi.co/trade-api/ws/v2"),
            HaltCode.ENDPOINT_SCHEME_PROHIBITED,
        )

    def test_wrong_port_rejected(self) -> None:
        self.assertEqual(
            _rest_halt_code("https://external-api.demo.kalshi.co:8443/trade-api/v2"),
            HaltCode.ENDPOINT_PORT_PROHIBITED,
        )

    def test_malformed_port_rejected(self) -> None:
        self.assertEqual(
            _rest_halt_code("https://external-api.demo.kalshi.co:notaport/trade-api/v2"),
            HaltCode.ENDPOINT_MALFORMED,
        )

    def test_wrong_path_rejected(self) -> None:
        self.assertEqual(
            _rest_halt_code("https://external-api.demo.kalshi.co/trade-api/v3"),
            HaltCode.ENDPOINT_PATH_PROHIBITED,
        )

    def test_trailing_slash_path_rejected(self) -> None:
        self.assertEqual(
            _rest_halt_code("https://external-api.demo.kalshi.co/trade-api/v2/"),
            HaltCode.ENDPOINT_PATH_PROHIBITED,
        )

    def test_duplicate_slash_path_rejected(self) -> None:
        self.assertEqual(
            _rest_halt_code("https://external-api.demo.kalshi.co//trade-api/v2"),
            HaltCode.ENDPOINT_MALFORMED,
        )

    def test_dot_segment_path_rejected(self) -> None:
        self.assertEqual(
            _rest_halt_code("https://external-api.demo.kalshi.co/trade-api/./v2"),
            HaltCode.ENDPOINT_MALFORMED,
        )

    def test_dot_dot_segment_path_rejected(self) -> None:
        self.assertEqual(
            _rest_halt_code("https://external-api.demo.kalshi.co/trade-api/../v2"),
            HaltCode.ENDPOINT_MALFORMED,
        )

    def test_percent_encoded_separator_rejected(self) -> None:
        self.assertEqual(
            _rest_halt_code("https://external-api.demo.kalshi.co/trade-api%2Fv2"),
            HaltCode.ENDPOINT_MALFORMED,
        )

    def test_whitespace_in_url_rejected(self) -> None:
        self.assertEqual(
            _rest_halt_code("https://external-api.demo.kalshi.co/trade-api/v2 "),
            HaltCode.ENDPOINT_MALFORMED,
        )

    def test_control_character_in_url_rejected(self) -> None:
        self.assertEqual(
            _rest_halt_code("https://external-api.demo.kalshi.co/trade-api/v2\x01"),
            HaltCode.ENDPOINT_MALFORMED,
        )

    def test_relative_url_rejected(self) -> None:
        self.assertEqual(_rest_halt_code("/trade-api/v2"), HaltCode.ENDPOINT_MALFORMED)

    def test_opaque_url_rejected(self) -> None:
        self.assertEqual(
            _rest_halt_code("mailto:ops@example.com"), HaltCode.ENDPOINT_MALFORMED
        )

    def test_both_endpoints_required_even_for_rest_only_capability(self) -> None:
        # A syntactically-fine REST endpoint does not mask a bad WebSocket
        # endpoint, even though the requested capability is REST-only.
        result = validate(
            _config(_DEMO_REST, "wss://malicious.example/trade-api/ws/v2")
        )
        self.assertIsNone(result.success)
        self.assertEqual(result.halt.code, HaltCode.ENDPOINT_HOST_PROHIBITED)

    def test_endpoint_failure_never_returns_partial_profile(self) -> None:
        result = validate(_config("", _DEMO_WS))
        self.assertIsNone(result.success)


if __name__ == "__main__":
    unittest.main()
