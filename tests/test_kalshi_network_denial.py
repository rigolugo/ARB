"""Network-denial instrumentation and static import/socket-use scan
(Candidate 02 Section 20.1 / handoff Section 12 "Network denial").

Patches and counts `socket.getaddrinfo`, `socket.socket`,
`socket.create_connection`, and `urllib.request.urlopen`. Representative
success and failure validations must report zero calls. An AST scan over
the authorized production modules rejects prohibited imports and direct
`socket` use.
"""

from __future__ import annotations

import ast
import os
import socket
import unittest
import urllib.request
from unittest import mock

from arb.venues.kalshi import (
    AuthorizationValue as AV,
    NonSecretConfigurationInput as Input,
    RequestedCapability as RC,
    TaskAuthorizationCapabilityEnvelope as Envelope,
    validate,
)

_DEMO_REST = "https://external-api.demo.kalshi.co/trade-api/v2"
_DEMO_WS = "wss://external-api-ws.demo.kalshi.co/trade-api/ws/v2"

_PROHIBITED_IMPORTS = {
    "requests",
    "httpx",
    "aiohttp",
    "websockets",
    "kalshi",
    "kalshi_python",
    "cryptography",
    "urllib.request",
    "http.client",
    "subprocess",
}

_PRODUCTION_MODULE_PATHS = (
    "src/arb/__init__.py",
    "src/arb/venues/__init__.py",
    "src/arb/venues/kalshi/__init__.py",
    "src/arb/venues/kalshi/models.py",
    "src/arb/venues/kalshi/errors.py",
    "src/arb/venues/kalshi/serialization.py",
    "src/arb/venues/kalshi/validation.py",
)


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


class NetworkDenialCounterTests(unittest.TestCase):
    def _run_with_network_counters(self, config: Input):
        with mock.patch.object(
            socket, "getaddrinfo", side_effect=AssertionError("network denied")
        ) as getaddrinfo, mock.patch.object(
            socket, "socket", side_effect=AssertionError("network denied")
        ) as socket_ctor, mock.patch.object(
            socket, "create_connection", side_effect=AssertionError("network denied")
        ) as create_connection, mock.patch.object(
            urllib.request, "urlopen", side_effect=AssertionError("network denied")
        ) as urlopen:
            result = validate(config)
            counters = {
                "getaddrinfo": getaddrinfo.call_count,
                "socket": socket_ctor.call_count,
                "create_connection": create_connection.call_count,
                "urlopen": urlopen.call_count,
            }
        return result, counters

    def test_successful_validation_makes_zero_network_calls(self) -> None:
        result, counters = self._run_with_network_counters(_config())
        self.assertIsNotNone(result.success)
        self.assertEqual(sum(counters.values()), 0)

    def test_halted_validation_makes_zero_network_calls(self) -> None:
        result, counters = self._run_with_network_counters(
            _config(environment="KALSHI_PRODUCTION")
        )
        self.assertIsNotNone(result.halt)
        self.assertEqual(sum(counters.values()), 0)

    def test_endpoint_rejection_makes_zero_network_calls(self) -> None:
        result, counters = self._run_with_network_counters(
            _config(rest_endpoint="https://malicious.example/trade-api/v2")
        )
        self.assertIsNotNone(result.halt)
        self.assertEqual(sum(counters.values()), 0)

    def test_authenticated_read_validation_makes_zero_network_calls(self) -> None:
        from arb.venues.kalshi import (
            CredentialReferenceKind as CRK,
            CredentialReferenceState as CRS,
            CredentialSourceReference,
        )

        references = (
            CredentialSourceReference(
                CRK.API_KEY_ID_ENV_SOURCE, "KALSHI_DEMO_API_KEY_ID", CRS.CONFIGURED
            ),
            CredentialSourceReference(
                CRK.PRIVATE_KEY_PEM_ENV_SOURCE,
                "KALSHI_DEMO_PRIVATE_KEY_PEM",
                CRS.CONFIGURED,
            ),
        )
        result, counters = self._run_with_network_counters(
            _config(
                requested_capability=RC.DEMO_AUTHENTICATED_READ.value,
                capability_envelope=_envelope(
                    demo_authenticated_reads=AV.PERMITTED, credential_use=AV.PERMITTED
                ),
                credential_references=references,
            )
        )
        self.assertIsNotNone(result.success)
        self.assertEqual(sum(counters.values()), 0)


class StaticImportAndSocketScanTests(unittest.TestCase):
    def _repo_root(self) -> str:
        here = os.path.dirname(os.path.abspath(__file__))
        return os.path.dirname(here)

    def _iter_import_names(self, tree: ast.AST):
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    yield alias.name
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    yield node.module

    def test_no_prohibited_imports_in_production_modules(self) -> None:
        root = self._repo_root()
        for relative_path in _PRODUCTION_MODULE_PATHS:
            full_path = os.path.join(root, relative_path)
            with self.subTest(module=relative_path):
                with open(full_path, "r", encoding="utf-8") as handle:
                    source = handle.read()
                tree = ast.parse(source, filename=full_path)
                found_prohibited = {
                    name
                    for name in self._iter_import_names(tree)
                    if name in _PROHIBITED_IMPORTS
                    or any(name.startswith(prefix + ".") for prefix in _PROHIBITED_IMPORTS)
                }
                self.assertEqual(
                    found_prohibited,
                    set(),
                    f"prohibited import(s) found in {relative_path}: {found_prohibited}",
                )

    def test_no_direct_socket_module_use_in_production_modules(self) -> None:
        root = self._repo_root()
        for relative_path in _PRODUCTION_MODULE_PATHS:
            full_path = os.path.join(root, relative_path)
            with self.subTest(module=relative_path):
                with open(full_path, "r", encoding="utf-8") as handle:
                    source = handle.read()
                tree = ast.parse(source, filename=full_path)
                imports_socket = "socket" in set(self._iter_import_names(tree))
                self.assertFalse(
                    imports_socket, f"direct socket import found in {relative_path}"
                )

    def test_only_urllib_parse_used_for_url_handling(self) -> None:
        root = self._repo_root()
        validation_path = os.path.join(
            root, "src/arb/venues/kalshi/validation.py"
        )
        with open(validation_path, "r", encoding="utf-8") as handle:
            source = handle.read()
        tree = ast.parse(source, filename=validation_path)
        import_names = set(self._iter_import_names(tree))
        self.assertIn("urllib.parse", import_names)
        self.assertNotIn("urllib.request", import_names)


if __name__ == "__main__":
    unittest.main()
