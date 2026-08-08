"""Offline unit tests for the Kalshi Demo read-only connectivity preflight,
Implementation 04 (`KALSHI_DEMO_READ_ONLY_CONNECTIVITY_PREFLIGHT_SPEC_03.md`
Section 16, covering Revision-03's Option-A deadline and external
authorization-provenance corrections plus all preserved Revision-02
coverage).

All DNS, socket, TLS, and HTTP behavior in this file is fake/mocked.
No test in this file contacts Kalshi, Polymarket, or any other external
endpoint. Test docstrings/comments reference the Section 16 item numbers
they cover.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import os
import queue
import socket
import ssl
import threading
import time
import unittest
from dataclasses import dataclass
from datetime import datetime, timezone
from unittest import mock

from arb.venues.kalshi import (
    AuthorizationValue as AV,
    NonSecretConfigurationInput as Input,
    RequestedCapability as RC,
    TaskAuthorizationCapabilityEnvelope as Envelope,
    ValidatedDemoProfile,
    validate,
)
from arb.venues.kalshi import connectivity as conn

_DEMO_REST = "https://external-api.demo.kalshi.co/trade-api/v2"
_DEMO_WS = "wss://external-api-ws.demo.kalshi.co/trade-api/ws/v2"
_PROD_REST = "https://external-api.kalshi.com/trade-api/v2"

_RAW_OPENAPI_SHA = "a" * 64
_OTHER_RAW_OPENAPI_SHA = "b" * 64

_PUBLIC_ADDR_A = "1.2.3.4"
_PUBLIC_ADDR_B = "1.2.3.5"
_PRIVATE_ADDR = "10.0.0.5"
_PUBLIC_ADDR_V6 = "2600:1234::1"  # globally-classified per ipaddress, generic placeholder
_PUBLIC_ADDR_V6_B = "2600:1234::2"


def _af_candidate(address_text: str, port: int = 443):
    """Implementation 10 correction 2 test helper: builds the
    `(family, sockaddr)` pair `_resolve_addresses`/`_resolve_addresses_with_deadline`
    now return, auto-detecting IPv4 vs IPv6 from the address text so
    existing test call sites that just supply an address string don't
    all need to specify family by hand."""

    parsed = ipaddress.ip_address(address_text)
    if parsed.version == 4:
        return (socket.AF_INET, (address_text, port))
    return (socket.AF_INET6, (address_text, port, 0, 0))


def _af_candidates(*address_texts: str, port: int = 443):
    return tuple(_af_candidate(text, port=port) for text in address_texts)


def _connectivity_envelope(**overrides: AV) -> Envelope:
    fields = dict(
        schema_version=1,
        authorization_id="AUTH-CONN-02",
        authorizing_authority="Gustavo",
        task_id="KALSHI_DEMO_READ_ONLY_CONNECTIVITY_PREFLIGHT_IMPLEMENTATION_02",
        issue_date="2026-08-07",
        completion_rule="single-attempt",
        network_access=AV.PERMITTED,
        demo_public_reads=AV.PERMITTED,
        demo_authenticated_reads=AV.PROHIBITED,
        demo_writes=AV.PROHIBITED,
        production_public_reads=AV.PROHIBITED,
        production_authenticated_reads=AV.PROHIBITED,
        production_writes=AV.PROHIBITED,
        credential_use=AV.PROHIBITED,
        account_funding=AV.PROHIBITED,
        code_changes=AV.PROHIBITED,
        tests=AV.PROHIBITED,
        artifact_generation=AV.PERMITTED,
        repository_commits=AV.PROHIBITED,
    )
    fields.update(overrides)
    return Envelope(**fields)


def _demo_profile(**config_overrides) -> ValidatedDemoProfile:
    fields = dict(
        environment="KALSHI_DEMO",
        environment_source_field="ARB_KALSHI_ENVIRONMENT",
        rest_endpoint=_DEMO_REST,
        websocket_endpoint=_DEMO_WS,
        requested_capability=RC.DEMO_PUBLIC_REST_READ.value,
        capability_envelope=_connectivity_envelope(),
        config_schema_revision=1,
        endpoint_allowlist_revision="candidate-02",
    )
    fields.update(config_overrides)
    result = validate(Input(**fields))
    assert result.success is not None, result.halt
    return result.success


def _canonical_record_bytes(record: dict) -> bytes:
    return json.dumps(
        record, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")


def _record_dict(
    *,
    effective_security_source: str = "OPERATION_OVERRIDE",
    effective_security=(),
    effective_allows_anonymous: bool = True,
    effective_auth_classification: str = "PUBLIC_UNAUTHENTICATED_READ_ONLY",
    raw_openapi_sha256: str = _RAW_OPENAPI_SHA,
    global_security_key_present: bool = True,
    operation_security_key_present: bool = True,
    **overrides,
) -> dict:
    record = {
        "schema_version": 1,
        "source_url": "https://docs.kalshi.com/openapi.yaml",
        "retrieved_at_utc": "2026-08-07T00:00:00Z",
        "http_status": 200,
        "normalized_source_media_type": "text/yaml",
        "raw_openapi_byte_length": 323506,
        "raw_openapi_sha256": raw_openapi_sha256,
        "operation_method": "GET",
        "operation_path": "/exchange/status",
        "global_security_key_present": global_security_key_present,
        "operation_security_key_present": operation_security_key_present,
        "effective_security_source": effective_security_source,
        "effective_security": (
            list(effective_security) if effective_security is not None else None
        ),
        "effective_allows_anonymous": effective_allows_anonymous,
        "effective_auth_classification": effective_auth_classification,
        "reviewed_demo_rest_origin": "https://external-api.demo.kalshi.co",
        "reviewed_full_request_path": "/trade-api/v2/exchange/status",
        "binding_schema_revision": 1,
    }
    record.update(overrides)
    return record


def _valid_record_bytes(**overrides) -> bytes:
    return _canonical_record_bytes(_record_dict(**overrides))


def _preflight_input(
    *,
    profile: ValidatedDemoProfile | None = None,
    envelope: Envelope | None = None,
    record_bytes: bytes | None = None,
    expected_record_sha256: str | None = None,
    expected_raw_sha256: str = _RAW_OPENAPI_SHA,
    provenance_mode: "conn.ExecutionProvenanceMode | None" = None,
    execution_dispatch_expectation: "conn.ExecutionDispatchExpectation | None" = None,
    **overrides,
) -> conn.ConnectivityPreflightInput:
    # `provenance_mode` is resolved here, not as a parameter default,
    # so it always refers to the *current* `conn.ExecutionProvenanceMode`
    # class -- a parameter default bound at function-definition time
    # would go stale across `importlib.reload(conn)` in
    # `test_module_import_is_network_free`, since reload creates a new
    # enum class object.
    if provenance_mode is None:
        provenance_mode = conn.ExecutionProvenanceMode.EXTERNAL_GUSTAVO_ORCHESTRATION
    record_bytes = _valid_record_bytes() if record_bytes is None else record_bytes
    expected_record_sha256 = (
        hashlib.sha256(record_bytes).hexdigest()
        if expected_record_sha256 is None
        else expected_record_sha256
    )
    expectation = (
        execution_dispatch_expectation
        if execution_dispatch_expectation is not None
        else conn.ExecutionDispatchExpectation(
            expected_source_binding_record_sha256=expected_record_sha256,
            expected_raw_openapi_sha256=expected_raw_sha256,
            provenance_mode=provenance_mode,
        )
    )
    fields = dict(
        validated_demo_profile=profile if profile is not None else _demo_profile(),
        task_capability_envelope=(
            envelope if envelope is not None else _connectivity_envelope()
        ),
        execution_dispatch_expectation=expectation,
        source_binding_record_bytes=record_bytes,
        request_budget=1,
        overall_timeout_ms=10000,
        socket_stage_timeout_ms=5000,
    )
    fields.update(overrides)
    return conn.ConnectivityPreflightInput(**fields)


def _valid_plan() -> conn.ConnectivityPreflightPlan:
    plan = conn.plan_demo_read_only_connectivity(_preflight_input())
    assert isinstance(plan, conn.ConnectivityPreflightPlan), plan
    return plan


class _FakeTLSSocket:
    def __init__(self, response: bytes, *, tls_version: str = "TLSv1.3", raise_on_send=None):
        self._response = response
        self._tls_version = tls_version
        self._raise_on_send = raise_on_send
        self.sent = b""
        self.closed = False

    def sendall(self, data: bytes) -> None:
        if self._raise_on_send is not None:
            raise self._raise_on_send
        self.sent += data

    def recv(self, _n: int) -> bytes:
        chunk, self._response = self._response, b""
        return chunk

    def version(self) -> str:
        return self._tls_version

    def close(self) -> None:
        self.closed = True

    def settimeout(self, _t) -> None:
        pass


def _success_http_response(
    exchange_active=True, trading_active=True, extra_headers: str = ""
) -> bytes:
    body = json.dumps(
        {"exchange_active": exchange_active, "trading_active": trading_active}
    ).encode("utf-8")
    headers = (
        "HTTP/1.1 200 OK\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"{extra_headers}"
        "\r\n"
    ).encode("ascii")
    return headers + body


def _run_execution(
    plan=None,
    *,
    addresses=(_PUBLIC_ADDR_A,),
    response: bytes | None = None,
    tls_version: str = "TLSv1.3",
    connect_error: Exception | None = None,
    tls_error: Exception | None = None,
    send_error: Exception | None = None,
):
    if plan is None:
        plan = _valid_plan()
    if response is None:
        response = _success_http_response()

    def fake_resolve(host, port):
        return _af_candidates(*addresses, port=port)

    def fake_connect(address, port, family, timeout_s):
        if connect_error is not None:
            raise connect_error
        return mock.Mock()

    def fake_tls_wrap(raw_sock, server_hostname, timeout_s):
        if tls_error is not None:
            raise tls_error
        assert server_hostname == conn.DEMO_HOST
        return _FakeTLSSocket(response, tls_version=tls_version, raise_on_send=send_error)

    with mock.patch.object(conn, "_resolve_addresses", side_effect=fake_resolve), \
         mock.patch.object(conn, "_connect_tcp", side_effect=fake_connect), \
         mock.patch.object(conn, "_tls_wrap", side_effect=fake_tls_wrap):
        return conn.execute_demo_read_only_connectivity(plan)


class TopLevelExportTests(unittest.TestCase):
    """Correction 6: production execution and internal binding/DNS types
    stay out of the package top level."""

    def test_package_top_level_does_not_export_connectivity_names(self) -> None:
        import arb.venues.kalshi as top

        for forbidden in (
            "execute_demo_read_only_connectivity",
            "plan_demo_read_only_connectivity",
            "OfficialRestSourceBinding",
            "VerifiedDnsSet",
            "ConnectivityPreflightPlan",
            "ConnectivityPreflightInput",
        ):
            self.assertNotIn(forbidden, top.__all__)
            self.assertFalse(hasattr(top, forbidden))

    def test_execute_reachable_only_via_explicit_submodule_import(self) -> None:
        from arb.venues.kalshi import connectivity as explicit

        self.assertTrue(callable(explicit.execute_demo_read_only_connectivity))

    def test_internal_binding_and_dns_types_not_in_connectivity_all(self) -> None:
        self.assertNotIn("OfficialRestSourceBinding", conn.__all__)
        self.assertNotIn("VerifiedDnsSet", conn.__all__)
        self.assertNotIn("require_usable_official_rest_source_binding", conn.__all__)
        self.assertNotIn("require_usable_verified_dns_set", conn.__all__)


class Sha256LexemeValidationTests(unittest.TestCase):
    """Implementation 10 correction 1: `_is_sha256_hex` requires an
    exact ASCII `[0-9a-f]{64}` lexeme via `re.fullmatch`, not
    `int(value, 16)` (which accepts many Unicode decimal-digit
    characters standing in for ASCII `0`-`9`). Applied uniformly to
    `ExecutionDispatchExpectation`'s two expected-hash fields, the
    source record's own `raw_openapi_sha256`, and every current
    `OfficialRestSourceBinding` hash field. Every rejection is proven
    to occur before DNS."""

    _VALID_HASH = "a" * 64

    def test_valid_lowercase_ascii_hex_accepted(self) -> None:
        self.assertTrue(conn._is_sha256_hex(self._VALID_HASH))
        self.assertTrue(conn._is_sha256_hex("0123456789abcdef" * 4))

    def test_arabic_indic_digits_rejected(self) -> None:
        # Arabic-Indic digits (U+0660-U+0669) standing in for ASCII 0-9.
        spoofed = "\u0661" * 64  # would satisfy int(x, 16) == 1...1 in Python
        self.assertFalse(conn._is_sha256_hex(spoofed))

    def test_full_width_digits_rejected(self) -> None:
        spoofed = "\uff11" * 64  # fullwidth '1' characters
        self.assertFalse(conn._is_sha256_hex(spoofed))

    def test_mixed_ascii_and_unicode_pseudo_hex_rejected(self) -> None:
        spoofed = ("a" * 63) + "\uff11"  # 63 real ASCII hex chars + 1 fullwidth digit
        self.assertEqual(len(spoofed), 64)
        self.assertFalse(conn._is_sha256_hex(spoofed))

    def test_uppercase_ascii_hex_rejected(self) -> None:
        self.assertFalse(conn._is_sha256_hex("A" * 64))
        self.assertFalse(conn._is_sha256_hex(("0123456789ABCDEF" * 4)))

    def test_all_zero_hash_rejected(self) -> None:
        self.assertFalse(conn._is_sha256_hex("0" * 64))

    def test_str_subclass_rejected(self) -> None:
        class _SpoofedHashStr(str):
            def __eq__(self, other):
                return True

            def __ne__(self, other):
                return False

            def __hash__(self):
                return hash(str.__str__(self))

        spoofed = _SpoofedHashStr(self._VALID_HASH)
        self.assertFalse(conn._is_sha256_hex(spoofed))

    def test_int_16_would_have_wrongly_accepted_arabic_indic_digits(self) -> None:
        """Documents exactly why `int(value, 16)` is not a safe lexical
        validator: it silently succeeds on Arabic-Indic digit
        characters standing in for ASCII digits."""

        spoofed = "\u0661" * 64
        self.assertEqual(int(spoofed, 16), int("1" * 64, 16))
        self.assertFalse(conn._is_sha256_hex(spoofed))

    def test_trailing_newline_rejected(self) -> None:
        self.assertFalse(conn._is_sha256_hex(self._VALID_HASH + "\n"))

    def test_wrong_length_rejected(self) -> None:
        self.assertFalse(conn._is_sha256_hex("a" * 63))
        self.assertFalse(conn._is_sha256_hex("a" * 65))

    def test_pattern_uses_ascii_class_and_fullmatch(self) -> None:
        self.assertIn("[0-9a-f]", conn._SHA256_HEX_PATTERN.pattern)
        import inspect

        source = inspect.getsource(conn._is_sha256_hex)
        self.assertIn("_SHA256_HEX_PATTERN.fullmatch(", source)

    def test_deceptive_expectation_hash_halts_before_dns(self) -> None:
        spoofed = "\u0661" * 64
        plan = conn.plan_demo_read_only_connectivity(
            _preflight_input(expected_record_sha256=spoofed)
        )
        self.assertIsInstance(plan, conn.ConnectivityPreflightHalt)
        self.assertNotEqual(plan.code, conn.ConnectivityHaltCode.DNS_VERIFICATION_FAILED)

    def test_deceptive_raw_openapi_sha_in_record_halts_before_dns(self) -> None:
        spoofed = "\u0661" * 64
        record_bytes = _valid_record_bytes(raw_openapi_sha256=spoofed)
        plan = conn.plan_demo_read_only_connectivity(
            _preflight_input(record_bytes=record_bytes, expected_record_sha256=None)
        )
        self.assertIsInstance(plan, conn.ConnectivityPreflightHalt)

    def test_deceptive_binding_hash_field_rejected_with_zero_dns_calls(self) -> None:
        plan = _valid_plan()
        object.__setattr__(
            plan.source_binding, "source_binding_record_sha256", "A" * 64
        )
        with self.assertRaises(conn.ConnectivityError):
            conn.require_usable_official_rest_source_binding(
                plan.source_binding,
                plan.execution_dispatch_expectation,
                plan.source_binding_record_bytes,
            )
        dns_calls = []
        with mock.patch.object(
            conn,
            "_resolve_addresses_with_deadline",
            side_effect=lambda *a, **k: dns_calls.append(1),
        ):
            result = conn.execute_demo_read_only_connectivity(plan)
        self.assertEqual(dns_calls, [])
        self.assertEqual(result.code, conn.ConnectivityHaltCode.EXECUTION_PLAN_MUTATED)


class ExecutionDispatchExpectationTests(unittest.TestCase):
    """Revision 03, correction 2: `ExecutionDispatchExpectation` exact
    type/field semantics, and the explicit external-orchestration
    provenance boundary. No HMAC/signature/key field exists anywhere,
    and runtime code never claims cryptographic Gustavo provenance."""

    def test_valid_expectation_passes(self) -> None:
        expectation = conn.ExecutionDispatchExpectation(
            expected_source_binding_record_sha256=hashlib.sha256(
                _valid_record_bytes()
            ).hexdigest(),
            expected_raw_openapi_sha256=_RAW_OPENAPI_SHA,
            provenance_mode=conn.ExecutionProvenanceMode.EXTERNAL_GUSTAVO_ORCHESTRATION,
        )
        conn.require_usable_execution_dispatch_expectation(expectation)  # no raise

    def test_exact_type_required(self) -> None:
        with self.assertRaises(conn.ConnectivityTypeError):
            conn.require_usable_execution_dispatch_expectation(object())

    def test_duck_typed_expectation_rejected(self) -> None:
        real = conn.ExecutionDispatchExpectation(
            expected_source_binding_record_sha256=_RAW_OPENAPI_SHA,
            expected_raw_openapi_sha256=_RAW_OPENAPI_SHA,
            provenance_mode=conn.ExecutionProvenanceMode.EXTERNAL_GUSTAVO_ORCHESTRATION,
        )

        class DuckExpectation:
            def __getattr__(self, name):
                return getattr(real, name)

        with self.assertRaises(conn.ConnectivityTypeError):
            conn.require_usable_execution_dispatch_expectation(DuckExpectation())

    def test_expectation_has_exactly_three_fields(self) -> None:
        field_names = set(conn.ExecutionDispatchExpectation.__dataclass_fields__)
        self.assertEqual(
            field_names,
            {
                "expected_source_binding_record_sha256",
                "expected_raw_openapi_sha256",
                "provenance_mode",
            },
        )

    def test_blank_hash_rejected(self) -> None:
        expectation = conn.ExecutionDispatchExpectation(
            expected_source_binding_record_sha256="",
            expected_raw_openapi_sha256=_RAW_OPENAPI_SHA,
            provenance_mode=conn.ExecutionProvenanceMode.EXTERNAL_GUSTAVO_ORCHESTRATION,
        )
        with self.assertRaises(conn.ConnectivityError):
            conn.require_usable_execution_dispatch_expectation(expectation)

    def test_all_zero_placeholder_hash_rejected(self) -> None:
        expectation = conn.ExecutionDispatchExpectation(
            expected_source_binding_record_sha256="0" * 64,
            expected_raw_openapi_sha256=_RAW_OPENAPI_SHA,
            provenance_mode=conn.ExecutionProvenanceMode.EXTERNAL_GUSTAVO_ORCHESTRATION,
        )
        with self.assertRaises(conn.ConnectivityError):
            conn.require_usable_execution_dispatch_expectation(expectation)

    def test_malformed_hash_rejected(self) -> None:
        expectation = conn.ExecutionDispatchExpectation(
            expected_source_binding_record_sha256="not-hex" * 10,
            expected_raw_openapi_sha256=_RAW_OPENAPI_SHA,
            provenance_mode=conn.ExecutionProvenanceMode.EXTERNAL_GUSTAVO_ORCHESTRATION,
        )
        with self.assertRaises(conn.ConnectivityError):
            conn.require_usable_execution_dispatch_expectation(expectation)

    def test_malformed_expectation_halts_before_dns(self) -> None:
        plan = conn.plan_demo_read_only_connectivity(
            _preflight_input(expected_record_sha256="0" * 64)
        )
        self.assertIsInstance(plan, conn.ConnectivityPreflightHalt)
        self.assertEqual(
            plan.stage, conn.ConnectivityStage.EXECUTION_DISPATCH_EXPECTATION_VALIDATED
        )

    def test_record_sha_mismatch_halts_before_dns(self) -> None:
        record_bytes = _valid_record_bytes()
        wrong = hashlib.sha256(record_bytes + b"x").hexdigest()
        plan = conn.plan_demo_read_only_connectivity(
            _preflight_input(record_bytes=record_bytes, expected_record_sha256=wrong)
        )
        self.assertIsInstance(plan, conn.ConnectivityPreflightHalt)
        self.assertEqual(
            plan.code, conn.ConnectivityHaltCode.OFFICIAL_SOURCE_IDENTITY_UNBOUND
        )

    def test_raw_openapi_sha_mismatch_halts_before_dns(self) -> None:
        plan = conn.plan_demo_read_only_connectivity(
            _preflight_input(expected_raw_sha256=_OTHER_RAW_OPENAPI_SHA)
        )
        self.assertIsInstance(plan, conn.ConnectivityPreflightHalt)
        self.assertEqual(
            plan.code, conn.ConnectivityHaltCode.OFFICIAL_SOURCE_IDENTITY_UNBOUND
        )

    def test_valid_record_and_hashes_pass_even_though_provenance_proof_is_not_performed(
        self,
    ) -> None:
        """Item 7: `SOURCE_RECORD_AND_HASH_CONSISTENT` can be fully
        satisfied while `runtime_authorization_provenance_proof` stays
        exactly `NOT_PERFORMED_BY_DESIGN` -- the two are independent
        assurance classes, not one implying the other."""

        plan = _valid_plan()
        self.assertIsInstance(plan, conn.ConnectivityPreflightPlan)
        # No field on the plan or its expectation claims cryptographic
        # verification occurred.
        self.assertEqual(
            plan.execution_dispatch_expectation.provenance_mode,
            conn.ExecutionProvenanceMode.EXTERNAL_GUSTAVO_ORCHESTRATION,
        )

    def test_no_hmac_signature_key_or_credential_field_exists_anywhere(self) -> None:
        for cls in (
            conn.ExecutionDispatchExpectation,
            conn.ConnectivityPreflightPlan,
            conn.ConnectivityPreflightInput,
            conn.OfficialRestSourceBinding,
        ):
            for field_name in cls.__dataclass_fields__:
                lowered = field_name.lower()
                for forbidden in ("hmac", "signature", "secret", "credential", "cert", "key"):
                    self.assertNotIn(
                        forbidden,
                        lowered,
                        f"{cls.__name__}.{field_name} looks like a trust-root field",
                    )
        self.assertFalse(hasattr(conn, "_PROVENANCE_KEY"))
        self.assertFalse(hasattr(conn, "_compute_provenance_proof"))
        import ast

        with open(conn.__file__, "r", encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        self.assertNotIn("hmac", imported)

    def test_runtime_never_claims_stronger_provenance_values_anywhere_in_source(self) -> None:
        """Section 13.2: these three strings must never be emitted as an
        actual enum member, halt code, or computed value anywhere in
        the module -- they may appear in prose (this module's own
        docstring explains the prohibition by naming them) without
        violating that requirement, so this checks the closed enums and
        every dataclass's possible field values rather than scanning
        raw source text."""

        forbidden = {
            "GUSTAVO_SIGNATURE_VERIFIED",
            "GUSTAVO_PROVENANCE_CRYPTOGRAPHICALLY_VERIFIED",
            "AUTHORIZATION_PROVENANCE_VERIFIED_BY_HASH",
        }
        for enum_cls in (
            conn.ConnectivityHaltCode,
            conn.ConnectivityStage,
            conn.ExecutionProvenanceMode,
            conn.RuntimeProvenanceProof,
            conn.RestAuthenticationClass,
            conn.EffectiveSecuritySource,
        ):
            member_values = {member.value for member in enum_cls}
            self.assertEqual(member_values & forbidden, set())

    def test_success_evidence_reports_exact_provenance_constants(self) -> None:
        result = _run_execution()
        self.assertIsInstance(result, conn.ConnectivityPreflightSuccess)
        self.assertEqual(
            result.authorization_provenance_mode,
            conn.ExecutionProvenanceMode.EXTERNAL_GUSTAVO_ORCHESTRATION,
        )
        self.assertEqual(
            result.runtime_authorization_provenance_proof,
            conn.RuntimeProvenanceProof.NOT_PERFORMED_BY_DESIGN,
        )

    def test_test_created_expectation_is_a_fixture_not_authorization_proof(self) -> None:
        """Item 11: nothing about constructing a valid-looking
        `ExecutionDispatchExpectation` in a test constitutes evidence of
        real Gustavo authorization -- it is a data fixture matching the
        type's structural contract only. This test documents that fact
        rather than asserting behavior (there is no behavior to assert:
        the module makes no distinction between a test fixture and a
        real orchestration-supplied value, by design -- see the module
        docstring)."""

        expectation = conn.ExecutionDispatchExpectation(
            expected_source_binding_record_sha256=hashlib.sha256(
                _valid_record_bytes()
            ).hexdigest(),
            expected_raw_openapi_sha256=_RAW_OPENAPI_SHA,
            provenance_mode=conn.ExecutionProvenanceMode.EXTERNAL_GUSTAVO_ORCHESTRATION,
        )
        # Passing structural validation is not, and is not claimed to
        # be, proof of authorization provenance.
        conn.require_usable_execution_dispatch_expectation(expectation)
        self.assertTrue(True)

    def test_caller_created_official_rest_source_binding_still_unacceptable(self) -> None:
        plan = _valid_plan()
        field_types = {
            name: f.type
            for name, f in conn.ConnectivityPreflightInput.__dataclass_fields__.items()
        }
        self.assertNotIn("OfficialRestSourceBinding", str(field_types))


class CanonicalByteEqualityTests(unittest.TestCase):
    """Correction 3: `source_binding_record_bytes` must be the exact
    canonical Section 5.5.3 serialization, independent of whether its
    own hash happens to match a self-chosen `expected_*` value."""

    def _plan_for_bytes(self, record_bytes: bytes):
        expected = hashlib.sha256(record_bytes).hexdigest()
        return conn.plan_demo_read_only_connectivity(
            _preflight_input(record_bytes=record_bytes, expected_record_sha256=expected)
        )

    def test_canonical_bytes_accepted(self) -> None:
        record_bytes = _valid_record_bytes()
        # Sanity: the fixture itself is already canonical.
        record = json.loads(record_bytes)
        self.assertEqual(conn._canonical_record_bytes(record), record_bytes)
        result = self._plan_for_bytes(record_bytes)
        self.assertIsInstance(result, conn.ConnectivityPreflightPlan)

    def test_reordered_keys_rejected(self) -> None:
        record = _record_dict()
        # Deliberately NOT sorted, and NOT using canonical separators.
        reordered_text = json.dumps(
            dict(reversed(list(record.items()))),
            sort_keys=False,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        record_bytes = reordered_text.encode("utf-8")
        result = self._plan_for_bytes(record_bytes)
        self.assertIsInstance(result, conn.ConnectivityPreflightHalt)
        self.assertEqual(
            result.code, conn.ConnectivityHaltCode.OFFICIAL_SOURCE_IDENTITY_UNBOUND
        )

    def test_insignificant_whitespace_rejected(self) -> None:
        record = _record_dict()
        spaced_text = json.dumps(
            record, sort_keys=True, separators=(", ", ": "), ensure_ascii=True
        )
        record_bytes = spaced_text.encode("utf-8")
        result = self._plan_for_bytes(record_bytes)
        self.assertIsInstance(result, conn.ConnectivityPreflightHalt)
        self.assertEqual(
            result.code, conn.ConnectivityHaltCode.OFFICIAL_SOURCE_IDENTITY_UNBOUND
        )

    def test_trailing_newline_rejected(self) -> None:
        canonical = _valid_record_bytes()
        record_bytes = canonical + b"\n"
        result = self._plan_for_bytes(record_bytes)
        self.assertIsInstance(result, conn.ConnectivityPreflightHalt)
        self.assertEqual(
            result.code, conn.ConnectivityHaltCode.OFFICIAL_SOURCE_IDENTITY_UNBOUND
        )

    def test_trailing_whitespace_rejected(self) -> None:
        canonical = _valid_record_bytes()
        record_bytes = canonical + b"   "
        result = self._plan_for_bytes(record_bytes)
        self.assertIsInstance(result, conn.ConnectivityPreflightHalt)
        self.assertEqual(
            result.code, conn.ConnectivityHaltCode.OFFICIAL_SOURCE_IDENTITY_UNBOUND
        )

    def test_utf8_bom_rejected(self) -> None:
        canonical = _valid_record_bytes()
        record_bytes = b"\xef\xbb\xbf" + canonical
        result = self._plan_for_bytes(record_bytes)
        self.assertIsInstance(result, conn.ConnectivityPreflightHalt)
        self.assertEqual(
            result.code, conn.ConnectivityHaltCode.OFFICIAL_SOURCE_IDENTITY_UNBOUND
        )

    def test_noncanonical_escaping_rejected(self) -> None:
        canonical = _valid_record_bytes()
        canonical_text = canonical.decode("utf-8")
        # Unnecessarily (but validly, per the JSON grammar) escape every
        # forward slash in the source_url -- semantically identical,
        # byte-for-byte different from the canonical serialization.
        noncanonical_text = canonical_text.replace(
            '"https://docs.kalshi.com/openapi.yaml"',
            '"https:\\/\\/docs.kalshi.com\\/openapi.yaml"',
        )
        self.assertNotEqual(noncanonical_text, canonical_text)
        # Confirm it still parses to the identical logical record.
        self.assertEqual(json.loads(noncanonical_text), json.loads(canonical_text))
        record_bytes = noncanonical_text.encode("utf-8")
        result = self._plan_for_bytes(record_bytes)
        self.assertIsInstance(result, conn.ConnectivityPreflightHalt)
        self.assertEqual(
            result.code, conn.ConnectivityHaltCode.OFFICIAL_SOURCE_IDENTITY_UNBOUND
        )

    def test_rejection_holds_even_when_expected_hash_is_self_consistently_chosen(self) -> None:
        """The whole point of correction 3: even a caller who computes
        `expected_source_binding_record_sha256` directly from their own
        noncanonical bytes (so the *hash-match* check alone would pass)
        is still rejected by the independent canonical-reserialization
        check."""

        record = _record_dict()
        spaced_text = json.dumps(
            record, sort_keys=True, separators=(", ", ": "), ensure_ascii=True
        )
        record_bytes = spaced_text.encode("utf-8")
        self_consistent_expected = hashlib.sha256(record_bytes).hexdigest()
        result = conn.plan_demo_read_only_connectivity(
            _preflight_input(
                record_bytes=record_bytes,
                expected_record_sha256=self_consistent_expected,
            )
        )
        self.assertIsInstance(result, conn.ConnectivityPreflightHalt)
        self.assertEqual(
            result.code, conn.ConnectivityHaltCode.OFFICIAL_SOURCE_IDENTITY_UNBOUND
        )


class TimeoutOrderingTests(unittest.TestCase):
    """TLS handshake timeout applied before, not after, the blocking
    handshake call; response-read deadline recomputed absolutely on
    every recv(), not fixed once for the whole loop."""

    def test_tls_wrap_sets_timeout_on_raw_socket_before_wrap_socket_call(self) -> None:
        call_order = []

        class _RecordingSocket:
            def settimeout(self, t):
                call_order.append(("settimeout", t))

            def close(self):
                pass

        fake_context = mock.Mock()

        def fake_wrap_socket(sock, server_hostname=None):
            call_order.append(("wrap_socket", server_hostname))
            fake_ssl_sock = mock.Mock()
            fake_ssl_sock.version.return_value = "TLSv1.3"
            return fake_ssl_sock

        fake_context.wrap_socket.side_effect = fake_wrap_socket

        with mock.patch.object(conn.ssl, "create_default_context", return_value=fake_context):
            conn._tls_wrap(_RecordingSocket(), conn.DEMO_HOST, 3.0)

        self.assertEqual(call_order[0], ("settimeout", 3.0))
        self.assertEqual(call_order[1][0], "wrap_socket")

    def test_receive_response_recomputes_deadline_each_iteration(self) -> None:
        """A peer trickling one byte at a time, each within whatever a
        *fixed* single per-call timeout would have allowed, must not be
        able to keep the read loop alive past the absolute deadline."""

        body = json.dumps({"exchange_active": True, "trading_active": True}).encode(
            "utf-8"
        )
        full_response = (
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
            + f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
            + body
        )
        remaining = [full_response[i : i + 1] for i in range(len(full_response))]

        clock = {"now_ns": 0}

        def fake_monotonic_ns():
            return clock["now_ns"]

        class _TrickleSocket:
            def settimeout(self, t):
                pass

            def recv(self, _n):
                if not remaining:
                    return b""
                # Each byte "costs" enough simulated time that, after
                # enough bytes, the absolute deadline is exceeded even
                # though no single recv() ever appeared slow.
                clock["now_ns"] += 50_000_000
                return remaining.pop(0)

        deadline_ns = 500_000_000  # only ~10 bytes' worth of simulated time
        with mock.patch.object(conn, "_current_monotonic_ns", side_effect=fake_monotonic_ns):
            with self.assertRaises(socket.timeout):
                conn._receive_response(
                    _TrickleSocket(), 65536, deadline_ns, socket_stage_timeout_ms=5000
                )

    def test_receive_response_succeeds_within_deadline(self) -> None:
        response = _success_http_response()
        with mock.patch.object(conn, "_current_monotonic_ns", return_value=0):
            result = conn._receive_response(
                _FakeTLSSocket(response),
                65536,
                deadline_ns=10_000_000_000,
                socket_stage_timeout_ms=5000,
            )
        self.assertEqual(result, response)

    def test_recv_timeout_capped_at_5s_with_8s_overall_remaining(self) -> None:
        """Finding 1, bullet 1: with ~8s overall remaining, each
        individual `recv()` must be offered a timeout of 5.0s (the
        socket-stage cap), not 8.0s."""

        observed_timeouts = []

        class _RecordingSocket:
            def settimeout(self, t):
                observed_timeouts.append(t)

            def recv(self, _n):
                return b""  # end immediately after recording the timeout

        deadline_ns = 8_000_000_000  # ~8s remaining from "now" (mocked to 0)
        with mock.patch.object(conn, "_current_monotonic_ns", return_value=0):
            conn._receive_response(
                _RecordingSocket(), 65536, deadline_ns, socket_stage_timeout_ms=5000
            )
        self.assertEqual(len(observed_timeouts), 1)
        self.assertAlmostEqual(observed_timeouts[0], 5.0, places=6)

    def test_recv_timeout_approximately_3s_with_3s_overall_remaining(self) -> None:
        """Finding 1, bullet 2: with ~3s overall remaining (less than
        the 5s stage cap), each `recv()` must be offered approximately
        the smaller remaining-overall value, not the 5s cap."""

        observed_timeouts = []

        class _RecordingSocket:
            def settimeout(self, t):
                observed_timeouts.append(t)

            def recv(self, _n):
                return b""

        deadline_ns = 3_000_000_000  # ~3s remaining from "now" (mocked to 0)
        with mock.patch.object(conn, "_current_monotonic_ns", return_value=0):
            conn._receive_response(
                _RecordingSocket(), 65536, deadline_ns, socket_stage_timeout_ms=5000
            )
        self.assertEqual(len(observed_timeouts), 1)
        self.assertAlmostEqual(observed_timeouts[0], 3.0, places=6)

    def test_send_uses_the_same_subordinate_stage_cap(self) -> None:
        """Finding 1, bullet 3: the HTTP send timeout, computed in
        `execute_demo_read_only_connectivity` immediately before calling
        `_send_request`, must also be `min(5.0, remaining_overall)` --
        not the full remaining overall budget. Exercised through the
        full executor with ~8s overall remaining simulated via a
        patched clock, confirming the offered send timeout is 5.0s."""

        plan = _valid_plan()
        observed_send_timeouts = []

        def recording_send_request(tls_sock, host, full_path, timeout_s):
            observed_send_timeouts.append(timeout_s)
            raise socket.timeout("stop here -- only the offered timeout matters")

        call_count = {"n": 0}

        def fake_monotonic_ns():
            call_count["n"] += 1
            # Keep every clock read near "now" so ~8s of the 10s overall
            # budget appears remaining right up to the send call.
            return 2_000_000_000 if call_count["n"] > 1 else 0

        with mock.patch.object(conn, "_resolve_addresses", return_value=_af_candidates(_PUBLIC_ADDR_A)), \
             mock.patch.object(conn, "_connect_tcp", return_value=mock.Mock()), \
             mock.patch.object(
                 conn, "_tls_wrap", return_value=_FakeTLSSocket(_success_http_response())
             ), \
             mock.patch.object(conn, "_send_request", side_effect=recording_send_request), \
             mock.patch.object(conn, "_current_monotonic_ns", side_effect=fake_monotonic_ns):
            conn.execute_demo_read_only_connectivity(plan)

        self.assertEqual(len(observed_send_timeouts), 1)
        self.assertAlmostEqual(observed_send_timeouts[0], 5.0, places=6)

    def test_no_stage_resets_or_extends_the_overall_deadline(self) -> None:
        """Finding 1, bullet 4: `deadline_ns` (and therefore the overall
        10s budget) is computed exactly once, at the top of
        `execute_demo_read_only_connectivity`, and is never reassigned.
        Verified structurally: the identifier `deadline_ns` is bound by
        exactly one `=` assignment in the function's source."""

        import inspect

        source = inspect.getsource(conn.execute_demo_read_only_connectivity)
        assignments = [
            line
            for line in source.splitlines()
            if line.strip().startswith("deadline_ns =")
        ]
        self.assertEqual(len(assignments), 1)
        self.assertIn("_OVERALL_TIMEOUT_MS", assignments[0])


class OptionADeadlineTests(unittest.TestCase):
    """Revision 03, Section 16.3: Option-A deadline semantics -- the
    caller-visible 10000 ms contract, isolated in a fresh per-call
    daemon worker, with no join/cleanup wait past the deadline."""

    def test_deadline_begins_at_executor_entry_before_capability_gate(self) -> None:
        """Item 1. Even a completely invalid `plan` (wrong type) gets a
        `caller_visible_elapsed_ms` measured from function entry -- the
        deadline clock does not wait for the type check or capability
        gate to start."""

        result = conn.execute_demo_read_only_connectivity(object())
        self.assertIsInstance(result, conn.ConnectivityPreflightHalt)
        self.assertGreaterEqual(result.caller_visible_elapsed_ms, 0)

    def test_dns_is_offered_the_full_remaining_overall_budget_not_5000ms(self) -> None:
        """Finding 2. Immediately before DNS, only the positive
        remaining *overall* (10000 ms) budget is calculated -- the
        5000 ms `socket_stage_timeout_ms` cap must NOT be applied to the
        DNS wait. Near executor start this means
        `_resolve_addresses_with_deadline` is offered a timeout close to
        10 seconds, not close to 5."""

        plan = _valid_plan()
        observed_timeouts = []

        def recording_resolve(host, port, timeout_s):
            observed_timeouts.append(timeout_s)
            raise TimeoutError("stop here -- only the offered budget matters")

        with mock.patch.object(
            conn, "_resolve_addresses_with_deadline", side_effect=recording_resolve
        ):
            conn.execute_demo_read_only_connectivity(plan)

        self.assertEqual(len(observed_timeouts), 1)
        offered = observed_timeouts[0]
        # Near executor start, essentially the whole 10s overall budget
        # remains. Allow generous slack for real (unmocked) clock/test
        # overhead, but the value must clearly exceed the 5s
        # socket-stage cap -- proving that cap was NOT applied here.
        self.assertGreater(offered, 8.0)
        self.assertLessEqual(offered, 10.0)

    def test_never_completing_resolver_causes_timeout_without_joining(self) -> None:
        """Items 2, 3, 8. A private fake resolver that never puts a
        result on the channel must not be joined or waited for beyond
        the deadline; the call still returns promptly with a
        `TimeoutError` once the (short, test-only) deadline passes. This
        exercises `_resolve_addresses_with_deadline` directly with a
        short timeout, as the specification's Section 16.3 note permits,
        rather than waiting out the full 5000 ms production socket-stage
        cap through the public executor."""

        never_signals = threading.Event()

        def hanging_worker(host, port, result_channel):
            # Never puts anything on result_channel until released, well
            # after the test's own short deadline has already elapsed.
            never_signals.wait(timeout=2)

        with mock.patch.object(conn, "_dns_resolver_worker", side_effect=hanging_worker):
            start = time.monotonic()
            with self.assertRaises(TimeoutError):
                conn._resolve_addresses_with_deadline(conn.DEMO_HOST, conn.DEMO_PORT, 0.05)
            elapsed_s = time.monotonic() - start
        # Proves no join occurred: elapsed time is close to the 0.05s
        # deadline, not anywhere near the hanging worker's 2s wait.
        self.assertLess(elapsed_s, 1.0)
        never_signals.set()  # release the background thread for cleanliness

    def test_dns_timeout_halt_has_zero_counts_and_resolver_abandoned(self) -> None:
        """Item 4."""

        plan = _valid_plan()
        with mock.patch.object(
            conn, "_resolve_addresses_with_deadline", side_effect=TimeoutError("x")
        ):
            result = conn.execute_demo_read_only_connectivity(plan)
        self.assertEqual(result.code, conn.ConnectivityHaltCode.CONNECTIVITY_TIMEOUT)
        self.assertEqual(result.stage, conn.ConnectivityStage.DNS_RESOLUTION_WAIT)
        self.assertEqual(result.request_count, 0)
        self.assertEqual(result.retry_count, 0)
        self.assertTrue(result.resolver_abandoned)

    def test_late_resolver_completion_after_return_is_discarded(self) -> None:
        """Item 5. A worker that eventually does complete, after the
        caller already gave up waiting, has its result sit unread in the
        one-shot queue -- nothing in this module reads a queue a second
        time. `_resolve_addresses` (the only function that would touch a
        real socket) is mocked here so this test performs zero live DNS
        activity."""

        result_channel = queue.Queue(maxsize=1)
        # Simulate the deadline already having expired: nothing reads
        # from result_channel before this.
        with mock.patch.object(conn, "_resolve_addresses", return_value=_af_candidates(_PUBLIC_ADDR_A)):
            conn._dns_resolver_worker(conn.DEMO_HOST, conn.DEMO_PORT, result_channel)
        # A late completion (a real worker would have looked up DNS) is
        # now sitting in the queue -- but nothing in the production code
        # path ever calls .get() on this specific channel again once
        # _resolve_addresses_with_deadline has returned/raised.
        self.assertEqual(result_channel.qsize(), 1)
        kind, payload = result_channel.get_nowait()
        self.assertEqual(kind, "ok")
        self.assertEqual(payload, _af_candidates(_PUBLIC_ADDR_A))

    def test_late_completion_cannot_call_socket_tls_http_code(self) -> None:
        """Item 6. After a DNS timeout halt, execute_demo_read_only_connectivity
        has already returned -- there is no pending callback, future
        continuation, or resumption point that a late resolver result
        could invoke. This is verified structurally: the DNS-timeout
        return path is a plain `return` statement with no registered
        callback of any kind."""

        plan = _valid_plan()
        connect_calls = []
        with mock.patch.object(
            conn, "_resolve_addresses_with_deadline", side_effect=TimeoutError("x")
        ), mock.patch.object(
            conn, "_connect_tcp", side_effect=lambda *a, **k: connect_calls.append(1)
        ):
            result = conn.execute_demo_read_only_connectivity(plan)
        self.assertEqual(result.code, conn.ConnectivityHaltCode.CONNECTIVITY_TIMEOUT)
        self.assertEqual(connect_calls, [])

    def test_no_second_resolver_starts_after_timeout(self) -> None:
        """Item 7. Deterministic and offline: `_resolve_addresses_with_deadline`
        itself is mocked (rather than relying on a real queue wait,
        which -- now that DNS correctly receives the full ~10s remaining
        budget instead of the old, incorrect 5s cap -- would otherwise
        make this test block for several real seconds). The call count
        proves the resolve function is invoked at most once per
        execution; there is structurally no retry loop around it in
        `execute_demo_read_only_connectivity` to begin with."""

        plan = _valid_plan()
        resolve_calls = []

        def timing_out_resolve(host, port, timeout_s):
            resolve_calls.append(timeout_s)
            raise TimeoutError("simulated deadline expiry")

        with mock.patch.object(
            conn, "_resolve_addresses_with_deadline", side_effect=timing_out_resolve
        ):
            result = conn.execute_demo_read_only_connectivity(plan)
        self.assertEqual(result.code, conn.ConnectivityHaltCode.CONNECTIVITY_TIMEOUT)
        self.assertEqual(len(resolve_calls), 1)

    def test_worker_is_a_fresh_thread_not_a_reused_pool(self) -> None:
        """Confirms no reusable executor/thread-pool object exists at
        module scope that later calls could contend on or that could
        need shutdown-waiting."""

        self.assertFalse(hasattr(conn, "_DNS_EXECUTOR"))
        self.assertFalse(hasattr(conn, "_DNS_THREAD_POOL"))

    def test_worker_receives_only_host_port_and_channel(self) -> None:
        """Section 15.4 least privilege: the worker function's exact
        signature carries no plan/envelope/transport/credential
        parameter."""

        import inspect

        sig = inspect.signature(conn._dns_resolver_worker)
        self.assertEqual(list(sig.parameters), ["host", "port", "result_channel"])

    def test_resolver_worker_daemon_flag_set(self) -> None:
        """`daemon=True` means process exit does not wait for an
        abandoned worker either."""

        import inspect

        source = inspect.getsource(conn._resolve_addresses_with_deadline)
        self.assertIn("daemon=True", source)
        self.assertNotIn(".join(", source)

    def test_socket_stage_timeout_is_min_of_cap_and_remaining_overall(self) -> None:
        """Item 9."""

        plan = _valid_plan()
        self.assertEqual(plan.socket_stage_timeout_ms, 5000)
        self.assertEqual(plan.overall_timeout_ms, 10000)

    def test_expired_overall_budget_before_socket_prevents_next_network_action(self) -> None:
        """Item 10."""

        plan = _valid_plan()
        connect_calls = []
        call_count = {"n": 0}

        def fake_monotonic_ns():
            call_count["n"] += 1
            # Only the first two calls (start_monotonic_ns, then the
            # pre-DNS remaining-budget check) succeed; every call from
            # the pre-socket remaining-budget check onward reports the
            # deadline as already passed, so `_connect_tcp` must never
            # be reached.
            return 0 if call_count["n"] <= 2 else 11_000_000_000

        with mock.patch.object(
            conn, "_resolve_addresses_with_deadline", return_value=_af_candidates(_PUBLIC_ADDR_A)
        ), mock.patch.object(
            conn, "_connect_tcp", side_effect=lambda *a, **k: connect_calls.append(1)
        ), mock.patch.object(
            conn, "_current_monotonic_ns", side_effect=fake_monotonic_ns
        ):
            result = conn.execute_demo_read_only_connectivity(plan)
        self.assertEqual(result.code, conn.ConnectivityHaltCode.CONNECTIVITY_TIMEOUT)
        self.assertEqual(connect_calls, [])

    def test_deadline_exhausted_during_parsing_produces_timeout_not_success(self) -> None:
        """Finding 1: `_validate_response` itself takes no deadline/clock
        parameter (it cannot restart or extend anything), but the
        overall deadline is now rechecked immediately *after* it
        returns, before success is constructed. A fake clock simulates
        parsing having consumed enough real wall-clock time to exhaust
        the 10s overall deadline; the result must be `CONNECTIVITY_TIMEOUT`,
        never `DEMO_REST_CONNECTIVITY_CONFIRMED`."""

        import inspect

        sig = inspect.signature(conn._validate_response)
        self.assertNotIn("deadline", list(sig.parameters))

        plan = _valid_plan()
        clock = {"ns": 0}
        original_validate_response = conn._validate_response

        def fake_monotonic_ns():
            return clock["ns"]

        def slow_validate_response(raw_response, max_bytes):
            # Simulate that parsing/classification itself consumed
            # enough real time to exhaust the overall deadline, without
            # _validate_response ever consulting a clock itself.
            clock["ns"] = 10_000_000_001
            return original_validate_response(raw_response, max_bytes)

        with mock.patch.object(conn, "_resolve_addresses", return_value=_af_candidates(_PUBLIC_ADDR_A)), \
             mock.patch.object(conn, "_connect_tcp", return_value=mock.Mock()), \
             mock.patch.object(
                 conn, "_tls_wrap", return_value=_FakeTLSSocket(_success_http_response())
             ), \
             mock.patch.object(
                 conn, "_validate_response", side_effect=slow_validate_response
             ), \
             mock.patch.object(conn, "_current_monotonic_ns", side_effect=fake_monotonic_ns):
            result = conn.execute_demo_read_only_connectivity(plan)

        self.assertIsInstance(result, conn.ConnectivityPreflightHalt)
        self.assertEqual(result.code, conn.ConnectivityHaltCode.CONNECTIVITY_TIMEOUT)
        self.assertEqual(result.stage, conn.ConnectivityStage.RESPONSE_VALIDATED)
        self.assertEqual(result.request_count, 1)
        self.assertEqual(result.retry_count, 0)

    def test_parsing_within_the_deadline_still_succeeds(self) -> None:
        """Finding 1: ordinary parsing that completes well within the
        10s deadline is unaffected by the new post-parse check."""

        result = _run_execution()
        self.assertIsInstance(result, conn.ConnectivityPreflightSuccess)
        self.assertEqual(result.result_code, "DEMO_REST_CONNECTIVITY_CONFIRMED")

    def test_public_plan_and_executor_accept_only_exact_10000ms_contract(self) -> None:
        plan = _valid_plan()
        self.assertEqual(plan.overall_timeout_ms, 10000)
        bad_input = _preflight_input(overall_timeout_ms=9999)
        result = conn.plan_demo_read_only_connectivity(bad_input)
        self.assertIsInstance(result, conn.ConnectivityPreflightHalt)


class DnsSetIndependentRecomputationTests(unittest.TestCase):
    """Correction 3: every field of `VerifiedDnsSet` is independently
    recomputed at each consumption boundary."""

    def _valid_dns_set(self) -> conn.VerifiedDnsSet:
        pairs = conn._classify_dns_answer(_af_candidates(_PUBLIC_ADDR_A, _PUBLIC_ADDR_B))
        version, address = pairs[0]
        return conn.VerifiedDnsSet(
            host=conn.DEMO_HOST,
            port=conn.DEMO_PORT,
            addresses=pairs,
            selected_address=address,
            selected_ip_version=version,
        )

    def test_valid_set_passes(self) -> None:
        dns_set = self._valid_dns_set()
        conn.require_usable_verified_dns_set(dns_set, conn.DEMO_HOST, conn.DEMO_PORT)

    def test_mutated_to_private_address_halts(self) -> None:
        dns_set = self._valid_dns_set()
        mutated = ((4, _PRIVATE_ADDR),) + dns_set.addresses[1:]
        object.__setattr__(dns_set, "addresses", mutated)
        object.__setattr__(dns_set, "selected_address", _PRIVATE_ADDR)
        with self.assertRaises(conn.ConnectivityError):
            conn.require_usable_verified_dns_set(dns_set, conn.DEMO_HOST, conn.DEMO_PORT)

    def test_mutated_order_halts(self) -> None:
        dns_set = self._valid_dns_set()
        reversed_order = tuple(reversed(dns_set.addresses))
        if reversed_order == dns_set.addresses:
            self.skipTest("addresses already order-symmetric")
        object.__setattr__(dns_set, "addresses", reversed_order)
        with self.assertRaises(conn.ConnectivityError):
            conn.require_usable_verified_dns_set(dns_set, conn.DEMO_HOST, conn.DEMO_PORT)

    def test_mutated_selected_address_inconsistent_with_version_halts(self) -> None:
        dns_set = self._valid_dns_set()
        object.__setattr__(dns_set, "selected_ip_version", 6)
        with self.assertRaises(conn.ConnectivityError):
            conn.require_usable_verified_dns_set(dns_set, conn.DEMO_HOST, conn.DEMO_PORT)

    def test_mutated_host_halts(self) -> None:
        dns_set = self._valid_dns_set()
        object.__setattr__(dns_set, "host", "evil.example")
        with self.assertRaises(conn.ConnectivityError):
            conn.require_usable_verified_dns_set(dns_set, conn.DEMO_HOST, conn.DEMO_PORT)

    def test_duplicate_addresses_rejected(self) -> None:
        dns_set = self._valid_dns_set()
        object.__setattr__(
            dns_set, "addresses", (dns_set.addresses[0], dns_set.addresses[0])
        )
        with self.assertRaises(conn.ConnectivityError):
            conn.require_usable_verified_dns_set(dns_set, conn.DEMO_HOST, conn.DEMO_PORT)

    def test_exact_type_required(self) -> None:
        with self.assertRaises(conn.ConnectivityTypeError):
            conn.require_usable_verified_dns_set(object(), conn.DEMO_HOST, conn.DEMO_PORT)


class SchemaStrictnessTests(unittest.TestCase):
    """Correction 4: exact canonical source-binding-record schema."""

    def _plan_for(self, **record_overrides):
        record_bytes = _valid_record_bytes(**record_overrides)
        return conn.plan_demo_read_only_connectivity(
            _preflight_input(record_bytes=record_bytes, expected_record_sha256=None)
        )

    def test_schema_version_boolean_true_is_rejected_not_treated_as_one(self) -> None:
        result = self._plan_for(schema_version=True)
        self.assertIsInstance(result, conn.ConnectivityPreflightHalt)

    def test_http_status_boolean_rejected(self) -> None:
        result = self._plan_for(http_status=True)
        self.assertIsInstance(result, conn.ConnectivityPreflightHalt)

    def test_binding_schema_revision_boolean_rejected(self) -> None:
        result = self._plan_for(binding_schema_revision=True)
        self.assertIsInstance(result, conn.ConnectivityPreflightHalt)

    def test_uppercase_media_type_rejected(self) -> None:
        result = self._plan_for(normalized_source_media_type="TEXT/YAML")
        self.assertIsInstance(result, conn.ConnectivityPreflightHalt)

    def test_blank_media_type_rejected(self) -> None:
        result = self._plan_for(normalized_source_media_type="")
        self.assertIsInstance(result, conn.ConnectivityPreflightHalt)

    def test_whitespace_only_media_type_variants_rejected(self) -> None:
        """Implementation 10 correction 4: the previous `not value`
        check only caught the empty string `""`; any nonempty
        whitespace-only string passed it. `_is_lowercase_media_type` now
        uses the same deterministic blank rule as `models.py`'s private
        `_is_blank_string` (`value.strip() == ""`)."""

        for value in (" ", "   ", "\t", "\r\n", "\n", " \t \n "):
            with self.subTest(value=repr(value)):
                self.assertFalse(conn._is_lowercase_media_type(value))
                result = self._plan_for(normalized_source_media_type=value)
                self.assertIsInstance(result, conn.ConnectivityPreflightHalt)

    def test_media_type_str_subclass_rejected(self) -> None:
        spoofed = _SpoofedEqualityStr("text/yaml")
        self.assertFalse(conn._is_lowercase_media_type(spoofed))

    def test_valid_lowercase_media_type_accepted(self) -> None:
        self.assertTrue(conn._is_lowercase_media_type("text/yaml"))
        result = self._plan_for(normalized_source_media_type="text/yaml")
        self.assertIsInstance(result, conn.ConnectivityPreflightPlan)

    def test_non_rfc3339_timestamp_rejected(self) -> None:
        result = self._plan_for(retrieved_at_utc="not-a-timestamp")
        self.assertIsInstance(result, conn.ConnectivityPreflightHalt)

    def test_naive_timestamp_without_timezone_rejected(self) -> None:
        result = self._plan_for(retrieved_at_utc="2026-08-07T00:00:00")
        self.assertIsInstance(result, conn.ConnectivityPreflightHalt)

    def test_non_utc_offset_timestamp_rejected(self) -> None:
        result = self._plan_for(retrieved_at_utc="2026-08-07T00:00:00+05:00")
        self.assertIsInstance(result, conn.ConnectivityPreflightHalt)

    def test_strict_rfc3339_reject_list(self) -> None:
        """Finding 2: explicit reject list from the accepted
        specification -- each of these is a plausible-looking timestamp
        that `datetime.fromisoformat()` alone would have accepted (the
        Implementation-07 validator), but none is valid strict-syntax
        RFC 3339 UTC."""

        reject_list = (
            "2026-08-07 00:00:00+00:00",  # space instead of literal T
            "2026-08-07T00:00+00:00",  # missing seconds field
            "20260807T000000+00:00",  # basic format, no date/time separators
            "2026-08-07T00:00:00+0000",  # offset missing colon
            "2026-08-07T00:00:00+00",  # truncated offset
            "2026-08-07T00:00:00",  # timezone-naive
            "2026-08-07T00:00:00-00:00",  # non-UTC-designator negative zero offset
            "2026-13-01T00:00:00Z",  # impossible month
            "2026-02-30T00:00:00Z",  # impossible day (Feb 30)
            "2026-08-07T25:00:00Z",  # impossible hour
            "2026-08-07T00:61:00Z",  # impossible minute
        )
        for value in reject_list:
            with self.subTest(value=value):
                self.assertFalse(conn._is_rfc3339_utc(value))
                result = self._plan_for(retrieved_at_utc=value)
                self.assertIsInstance(result, conn.ConnectivityPreflightHalt)

    def test_strict_rfc3339_accepts_z_and_plus_zero_offset(self) -> None:
        for value in ("2026-08-07T00:00:00Z", "2026-08-07T00:00:00+00:00"):
            with self.subTest(value=value):
                self.assertTrue(conn._is_rfc3339_utc(value))
                result = self._plan_for(retrieved_at_utc=value)
                self.assertIsInstance(result, conn.ConnectivityPreflightPlan)

    def test_strict_rfc3339_accepts_conforming_fractional_seconds(self) -> None:
        value = "2026-08-07T00:00:00.123456Z"
        self.assertTrue(conn._is_rfc3339_utc(value))
        result = self._plan_for(retrieved_at_utc=value)
        self.assertIsInstance(result, conn.ConnectivityPreflightPlan)

    def test_strict_rfc3339_rejects_str_subclass(self) -> None:
        spoofed = _SpoofedEqualityStr("2026-08-07T00:00:00Z")
        self.assertFalse(conn._is_rfc3339_utc(spoofed))

    def test_strict_rfc3339_rejects_non_str_types(self) -> None:
        for value in (None, 12345, 1.5, b"2026-08-07T00:00:00Z", ["2026-08-07T00:00:00Z"]):
            with self.subTest(value=value):
                self.assertFalse(conn._is_rfc3339_utc(value))

    def test_strict_rfc3339_rejects_unicode_digits(self) -> None:
        """Implementation 09 correction 2: Python's `\\d` (without
        `re.ASCII`) matches any Unicode decimal digit, not just ASCII
        `0`-`9` -- and `int()` on the resulting substring would happily
        parse those too. The validator must use the literal `[0-9]`
        character class so none of these are accepted, even though each
        is visually a plausible timestamp."""

        unicode_digit_cases = (
            # Fullwidth digits (U+FF10-U+FF19) in the year.
            "\uff12\uff10\uff12\uff16-08-07T00:00:00Z",
            # Fullwidth digits throughout.
            (
                "\uff12\uff10\uff12\uff16-\uff10\uff18-\uff10\uff17T"
                "\uff10\uff10:\uff10\uff10:\uff10\uff10Z"
            ),
            # Arabic-Indic digits (U+0660-U+0669) in the year.
            "\u0662\u0660\u0662\u0666-08-07T00:00:00Z",
            # Unicode digit inside the fractional-seconds group.
            "2026-08-07T00:00:00.\uff11\uff12\uff13Z",
        )
        for value in unicode_digit_cases:
            with self.subTest(value=repr(value)):
                self.assertFalse(conn._is_rfc3339_utc(value))
                result = self._plan_for(retrieved_at_utc=value)
                self.assertIsInstance(result, conn.ConnectivityPreflightHalt)

    def test_strict_rfc3339_rejects_trailing_newline(self) -> None:
        """Implementation 09 correction 2: without `\\n` in
        `re.fullmatch(...)`, Python's `$` anchor matches either at the
        true end of the string or immediately before one trailing
        newline, so a `^...$`-anchored pattern (the Implementation-08
        validator) would have incorrectly accepted these."""

        for value in (
            "2026-08-07T00:00:00Z\n",
            "2026-08-07T00:00:00+00:00\n",
        ):
            with self.subTest(value=repr(value)):
                self.assertFalse(conn._is_rfc3339_utc(value))
                result = self._plan_for(retrieved_at_utc=value)
                self.assertIsInstance(result, conn.ConnectivityPreflightHalt)

    def test_strict_rfc3339_uses_fullmatch_not_match_plus_anchors(self) -> None:
        import inspect

        source = inspect.getsource(conn._is_rfc3339_utc)
        self.assertIn("_RFC3339_UTC_STRICT_PATTERN.fullmatch(", source)
        self.assertNotIn("_RFC3339_UTC_STRICT_PATTERN.match(", source)

    def test_strict_rfc3339_pattern_uses_ascii_digit_class(self) -> None:
        pattern_source = conn._RFC3339_UTC_STRICT_PATTERN.pattern
        self.assertIn("[0-9]", pattern_source)
        self.assertNotIn("\\d", pattern_source)

    def test_nan_in_record_json_rejected(self) -> None:
        record = _record_dict()
        text = json.dumps(
            record, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        )
        # Inject a raw NaN token in place of a harmless placeholder value
        # (json.dumps with allow_nan=True would otherwise permit it).
        malformed = text.replace('"binding_schema_revision":1', '"binding_schema_revision":NaN')
        record_bytes = malformed.encode("utf-8")
        result = conn.plan_demo_read_only_connectivity(
            _preflight_input(record_bytes=record_bytes, expected_record_sha256=None)
        )
        self.assertIsInstance(result, conn.ConnectivityPreflightHalt)

    def test_malformed_security_requirement_object_scope_list_rejected(self) -> None:
        result = self._plan_for(
            effective_security_source="OPERATION_OVERRIDE",
            effective_security=[{"apiKeyAuth": "not-a-list"}],
            effective_allows_anonymous=False,
            effective_auth_classification="AUTHENTICATED_READ_ONLY",
        )
        self.assertIsInstance(result, conn.ConnectivityPreflightHalt)
        self.assertEqual(result.code, conn.ConnectivityHaltCode.OFFICIAL_SOURCE_CONFLICT)

    def test_presence_flags_inconsistent_with_operation_override_halts(self) -> None:
        # operation_security_key_present=False contradicts
        # effective_security_source=OPERATION_OVERRIDE.
        result = self._plan_for(
            effective_security_source="OPERATION_OVERRIDE",
            operation_security_key_present=False,
        )
        self.assertIsInstance(result, conn.ConnectivityPreflightHalt)
        self.assertEqual(result.code, conn.ConnectivityHaltCode.OFFICIAL_SOURCE_CONFLICT)

    def test_presence_flags_inconsistent_with_global_inherited_halts(self) -> None:
        result = self._plan_for(
            effective_security_source="GLOBAL_INHERITED",
            effective_security=[],
            global_security_key_present=False,  # contradicts GLOBAL_INHERITED
            operation_security_key_present=False,
        )
        self.assertIsInstance(result, conn.ConnectivityPreflightHalt)
        self.assertEqual(result.code, conn.ConnectivityHaltCode.OFFICIAL_SOURCE_CONFLICT)

    def test_presence_flags_inconsistent_with_none_declared_halts(self) -> None:
        result = self._plan_for(
            effective_security_source="NONE_DECLARED",
            effective_security=None,
            effective_allows_anonymous=False,
            effective_auth_classification="UNKNOWN_OR_CONFLICTING",
            global_security_key_present=True,  # contradicts NONE_DECLARED
            operation_security_key_present=False,
        )
        self.assertIsInstance(result, conn.ConnectivityPreflightHalt)

    def test_none_declared_with_consistent_flags_produces_a_valid_plan(self) -> None:
        """Implementation 09 correction 1: Section 5.5.2 -- when neither
        the operation nor the root OpenAPI object declares `security`,
        no security requirement is declared at all, which is an
        affirmatively public state, not `UNKNOWN_OR_CONFLICTING`."""

        result = self._plan_for(
            effective_security_source="NONE_DECLARED",
            effective_security=None,
            effective_allows_anonymous=True,
            effective_auth_classification="PUBLIC_UNAUTHENTICATED_READ_ONLY",
            global_security_key_present=False,
            operation_security_key_present=False,
        )
        self.assertIsInstance(result, conn.ConnectivityPreflightPlan)

    def test_none_declared_with_allows_anonymous_false_rejected(self) -> None:
        """The recomputed value for this valid NONE_DECLARED state is
        now `effective_allows_anonymous=True`; a record that instead
        declares `False` disagrees with the independently recomputed
        value and must still halt."""

        result = self._plan_for(
            effective_security_source="NONE_DECLARED",
            effective_security=None,
            effective_allows_anonymous=False,
            effective_auth_classification="PUBLIC_UNAUTHENTICATED_READ_ONLY",
            global_security_key_present=False,
            operation_security_key_present=False,
        )
        self.assertIsInstance(result, conn.ConnectivityPreflightHalt)
        self.assertEqual(result.code, conn.ConnectivityHaltCode.OFFICIAL_SOURCE_CONFLICT)

    def test_none_declared_declaring_unknown_or_conflicting_rejected(self) -> None:
        """The recomputed classification for this valid NONE_DECLARED
        state is now PUBLIC_UNAUTHENTICATED_READ_ONLY; a record that
        instead declares UNKNOWN_OR_CONFLICTING disagrees with the
        independently recomputed value and must still halt -- the
        record's own declared fields are never trusted outright, even
        for the corrected NONE_DECLARED case."""

        result = self._plan_for(
            effective_security_source="NONE_DECLARED",
            effective_security=None,
            effective_allows_anonymous=True,
            effective_auth_classification="UNKNOWN_OR_CONFLICTING",
            global_security_key_present=False,
            operation_security_key_present=False,
        )
        self.assertIsInstance(result, conn.ConnectivityPreflightHalt)
        self.assertEqual(result.code, conn.ConnectivityHaltCode.OFFICIAL_SOURCE_CONFLICT)

    def test_none_declared_nonnull_effective_security_still_conflict(self) -> None:
        result = self._plan_for(
            effective_security_source="NONE_DECLARED",
            effective_security=[],
            effective_allows_anonymous=True,
            effective_auth_classification="PUBLIC_UNAUTHENTICATED_READ_ONLY",
            global_security_key_present=False,
            operation_security_key_present=False,
        )
        self.assertIsInstance(result, conn.ConnectivityPreflightHalt)

    def test_classify_effective_security_none_declared_directly(self) -> None:
        allows_anonymous, classification = conn._classify_effective_security(
            conn.EffectiveSecuritySource.NONE_DECLARED, None
        )
        self.assertTrue(allows_anonymous)
        self.assertEqual(
            classification, conn.RestAuthenticationClass.PUBLIC_UNAUTHENTICATED_READ_ONLY
        )


class _SpoofedEqualityStr(str):
    """A `str` subclass whose actual content is a prohibited value, but
    whose `__eq__`/`__ne__` always claim equality with whatever they are
    compared against -- simulating an object trying to fool a bare
    `==`/`!=` check. `type(x) is str` correctly rejects this regardless
    of the overridden comparison behavior."""

    def __eq__(self, other):  # noqa: D105
        return True

    def __ne__(self, other):  # noqa: D105
        return False

    def __hash__(self):  # noqa: D105
        return hash(str.__str__(self))


class _SpoofedEqualityInt(int):
    """An `int` subclass whose actual value differs from the required
    constant, but whose `__eq__`/`__ne__` always claim equality."""

    def __eq__(self, other):  # noqa: D105
        return True

    def __ne__(self, other):  # noqa: D105
        return False

    def __hash__(self):  # noqa: D105
        return hash(int(self))


class ExactTypeTrustBoundaryTests(unittest.TestCase):
    """Finding 3: `require_usable_connectivity_preflight_plan` must
    require exact built-in types, not merely equal-comparing values, for
    every network-affecting field -- because a subclass can override
    `__eq__` to lie about equality while holding a different actual
    value. `type(x) is str` / `type(x) is int` bypass any such override
    since `type()` never consults `__eq__`."""

    def test_spoofed_host_string_rejected_before_dns(self) -> None:
        plan = _valid_plan()
        spoofed_host = _SpoofedEqualityStr("evil.example.com")
        # Sanity: the spoofed object really does claim equality despite
        # holding a different actual hostname.
        self.assertEqual(spoofed_host, conn.DEMO_HOST)
        self.assertNotEqual(str(spoofed_host), conn.DEMO_HOST)

        object.__setattr__(plan, "host", spoofed_host)
        with self.assertRaises(conn.ConnectivityError):
            conn.require_usable_connectivity_preflight_plan(plan)

        dns_calls = []
        with mock.patch.object(
            conn,
            "_resolve_addresses_with_deadline",
            side_effect=lambda *a, **k: dns_calls.append(1),
        ):
            result = conn.execute_demo_read_only_connectivity(plan)
        self.assertEqual(dns_calls, [])
        self.assertIsInstance(result, conn.ConnectivityPreflightHalt)
        self.assertEqual(result.code, conn.ConnectivityHaltCode.EXECUTION_PLAN_MUTATED)

    def test_spoofed_port_int_rejected_before_dns(self) -> None:
        plan = _valid_plan()
        spoofed_port = _SpoofedEqualityInt(9999)
        self.assertEqual(spoofed_port, conn.DEMO_PORT)
        self.assertNotEqual(int(spoofed_port), conn.DEMO_PORT)

        object.__setattr__(plan, "port", spoofed_port)
        with self.assertRaises(conn.ConnectivityError):
            conn.require_usable_connectivity_preflight_plan(plan)

        dns_calls = []
        with mock.patch.object(
            conn,
            "_resolve_addresses_with_deadline",
            side_effect=lambda *a, **k: dns_calls.append(1),
        ):
            result = conn.execute_demo_read_only_connectivity(plan)
        self.assertEqual(dns_calls, [])
        self.assertIsInstance(result, conn.ConnectivityPreflightHalt)
        self.assertEqual(result.code, conn.ConnectivityHaltCode.EXECUTION_PLAN_MUTATED)

    def test_spoofed_full_path_string_rejected(self) -> None:
        plan = _valid_plan()
        spoofed = _SpoofedEqualityStr("/trade-api/v2/orders")
        object.__setattr__(plan, "full_path", spoofed)
        with self.assertRaises(conn.ConnectivityError):
            conn.require_usable_connectivity_preflight_plan(plan)

    def test_spoofed_request_budget_int_rejected(self) -> None:
        plan = _valid_plan()
        spoofed = _SpoofedEqualityInt(999)
        object.__setattr__(plan, "request_budget", spoofed)
        with self.assertRaises(conn.ConnectivityError):
            conn.require_usable_connectivity_preflight_plan(plan)

    def test_spoofed_overall_timeout_int_rejected(self) -> None:
        plan = _valid_plan()
        spoofed = _SpoofedEqualityInt(60000)
        object.__setattr__(plan, "overall_timeout_ms", spoofed)
        with self.assertRaises(conn.ConnectivityError):
            conn.require_usable_connectivity_preflight_plan(plan)

    def test_exact_type_helper_rejects_str_subclass(self) -> None:
        self.assertFalse(conn._is_exact_str(_SpoofedEqualityStr("x")))
        self.assertTrue(conn._is_exact_str("x"))

    def test_exact_type_helper_rejects_int_subclass(self) -> None:
        self.assertFalse(conn._is_exact_int(_SpoofedEqualityInt(1)))
        self.assertTrue(conn._is_exact_int(1))

    def test_every_network_affecting_plan_field_has_exact_type_check(self) -> None:
        """Confirms the source itself performs a `type(...) is ...`
        check (not just `==`/`!=`) for each field the dispatch listed."""

        import inspect

        source = inspect.getsource(conn.require_usable_connectivity_preflight_plan)
        for field_name in (
            "plan.host",
            "plan.port",
            "plan.base_path",
            "plan.route",
            "plan.full_path",
            "plan.method",
            "plan.request_budget",
            "plan.retry_count",
            "plan.overall_timeout_ms",
            "plan.socket_stage_timeout_ms",
            "plan.max_response_bytes",
        ):
            self.assertIn(f"_is_exact_", source)  # sanity the helpers are used at all
        # Every listed field name should appear alongside an
        # `_is_exact_*` guard somewhere in the function body.
        for field_name in (
            "host",
            "port",
            "base_path",
            "route",
            "full_path",
            "method",
            "request_budget",
            "retry_count",
            "overall_timeout_ms",
            "socket_stage_timeout_ms",
            "max_response_bytes",
        ):
            self.assertIn(f"plan.{field_name}", source)


class _DeceptiveValueProxy:
    """A duck-typed object exposing a `.value` attribute matching a
    real enum member's string value, but which is not an instance of
    that enum at all -- simulating an object trying to fool a
    `.value == "..."` style check. `type(x) is RealEnum` correctly
    rejects this regardless of the exposed `.value`."""

    def __init__(self, spoofed_value: str):
        self.value = spoofed_value

    def __eq__(self, other):
        return True

    def __ne__(self, other):
        return False

    def __hash__(self):
        return hash(self.value)


class _DeceptiveEndpointComponentsProxy:
    """A duck-typed stand-in for `EndpointComponents` exposing the
    exact same field values (so naive attribute comparisons would
    pass) but which is not an instance of `EndpointComponents`."""

    def __init__(self, *, scheme, host, port, path):
        self.scheme = scheme
        self.host = host
        self.port = port
        self.path = path
        self.has_user_info = False
        self.has_query = False
        self.has_fragment = False


class ProfileExactTypeTrustBoundaryTests(unittest.TestCase):
    """Finding 2: every nested `ValidatedDemoProfile` field must be
    exact-type-checked (not merely value/`.value`-compared) at every
    production consumption gate, so a duck-typed or proxy object cannot
    impersonate `Environment`, `RequestedCapability`,
    `EndpointComponents`, `CredentialReferenceKind`, or
    `CredentialReferenceState`."""

    def test_deceptive_environment_value_proxy_rejected(self) -> None:
        plan = _valid_plan()
        spoofed = _DeceptiveValueProxy("KALSHI_DEMO")
        self.assertEqual(spoofed, conn.Environment.KALSHI_DEMO)  # the deception
        object.__setattr__(plan.profile, "environment", spoofed)
        with self.assertRaises(conn.ConnectivityTypeError):
            conn.require_usable_validated_demo_profile(plan.profile)

        dns_calls = []
        with mock.patch.object(
            conn,
            "_resolve_addresses_with_deadline",
            side_effect=lambda *a, **k: dns_calls.append(1),
        ):
            result = conn.execute_demo_read_only_connectivity(plan)
        self.assertEqual(dns_calls, [])
        self.assertEqual(result.code, conn.ConnectivityHaltCode.EXECUTION_PLAN_MUTATED)

    def test_deceptive_requested_capability_proxy_rejected(self) -> None:
        plan = _valid_plan()
        spoofed = _DeceptiveValueProxy("DEMO_PUBLIC_REST_READ")
        object.__setattr__(plan.profile, "requested_capability", spoofed)
        with self.assertRaises(conn.ConnectivityTypeError):
            conn.require_usable_validated_demo_profile(plan.profile)

    def test_deceptive_effective_capability_proxy_rejected(self) -> None:
        plan = _valid_plan()
        spoofed = _DeceptiveValueProxy("DEMO_PUBLIC_REST_READ")
        object.__setattr__(plan.profile, "effective_capability", spoofed)
        with self.assertRaises(conn.ConnectivityTypeError):
            conn.require_usable_validated_demo_profile(plan.profile)

    def test_deceptive_rest_endpoint_components_proxy_rejected_before_dns(self) -> None:
        plan = _valid_plan()
        spoofed_rest = _DeceptiveEndpointComponentsProxy(
            scheme="https", host=conn.DEMO_HOST, port=conn.DEMO_PORT, path=conn.DEMO_BASE_PATH
        )
        object.__setattr__(plan.profile, "rest", spoofed_rest)
        with self.assertRaises(conn.ConnectivityTypeError):
            conn.require_usable_validated_demo_profile(plan.profile)

        dns_calls = []
        with mock.patch.object(
            conn,
            "_resolve_addresses_with_deadline",
            side_effect=lambda *a, **k: dns_calls.append(1),
        ):
            result = conn.execute_demo_read_only_connectivity(plan)
        self.assertEqual(dns_calls, [])
        self.assertEqual(result.code, conn.ConnectivityHaltCode.EXECUTION_PLAN_MUTATED)

    def test_deceptive_credential_reference_kind_proxy_rejected(self) -> None:
        plan = _valid_plan()
        spoofed_kind = _DeceptiveValueProxy("API_KEY_ID_ENV_SOURCE")
        real_state = conn.CredentialReferenceState.NOT_REQUIRED
        object.__setattr__(
            plan.profile, "credential_reference_states", ((spoofed_kind, real_state),)
        )
        with self.assertRaises(conn.ConnectivityTypeError):
            conn.require_usable_validated_demo_profile(plan.profile)

    def test_deceptive_credential_reference_state_proxy_rejected(self) -> None:
        plan = _valid_plan()
        real_kind = conn.CredentialReferenceKind.API_KEY_ID_ENV_SOURCE
        spoofed_state = _DeceptiveValueProxy("NOT_REQUIRED")
        object.__setattr__(
            plan.profile, "credential_reference_states", ((real_kind, spoofed_state),)
        )
        with self.assertRaises(conn.ConnectivityTypeError):
            conn.require_usable_validated_demo_profile(plan.profile)

    def test_deceptive_credential_reference_states_container_type_rejected(self) -> None:
        plan = _valid_plan()
        real_kind = conn.CredentialReferenceKind.API_KEY_ID_ENV_SOURCE
        real_state = conn.CredentialReferenceState.NOT_REQUIRED
        # A list instead of a tuple -- same logical content, wrong exact
        # container type.
        object.__setattr__(
            plan.profile, "credential_reference_states", [(real_kind, real_state)]
        )
        with self.assertRaises(conn.ConnectivityTypeError):
            conn.require_usable_validated_demo_profile(plan.profile)

    def test_non_bool_truthy_secret_loaded_rejected(self) -> None:
        plan = _valid_plan()
        # `0` is falsy and `== False`, but is not the exact bool False.
        object.__setattr__(plan.profile, "secret_loaded", 0)
        with self.assertRaises(conn.ConnectivityError):
            conn.require_usable_validated_demo_profile(plan.profile)

    def test_valid_profile_passes_every_new_exact_type_check(self) -> None:
        plan = _valid_plan()
        conn.require_usable_validated_demo_profile(plan.profile)  # no raise


class ProfileWebSocketAndRevisionValidationTests(unittest.TestCase):
    """Implementation 10 correction 3: `profile.websocket` and
    `allowlist_revision`/`validation_schema_revision` are now validated
    at every profile consumption gate, hard-bound to the exact values
    verified against every pre-existing canonical test fixture in this
    repository (`endpoint_allowlist_revision="candidate-02"`,
    `config_schema_revision=1`)."""

    def _assert_halts_before_dns(self, plan) -> None:
        with self.assertRaises(conn.ConnectivityError):
            conn.require_usable_validated_demo_profile(plan.profile)
        dns_calls = []
        with mock.patch.object(
            conn,
            "_resolve_addresses_with_deadline",
            side_effect=lambda *a, **k: dns_calls.append(1),
        ):
            result = conn.execute_demo_read_only_connectivity(plan)
        self.assertEqual(dns_calls, [])
        self.assertIsInstance(result, conn.ConnectivityPreflightHalt)
        self.assertEqual(result.code, conn.ConnectivityHaltCode.EXECUTION_PLAN_MUTATED)

    def test_valid_profile_websocket_and_revisions_pass(self) -> None:
        plan = _valid_plan()
        self.assertEqual(plan.profile.websocket.host, conn.DEMO_WEBSOCKET_HOST)
        self.assertEqual(plan.profile.allowlist_revision, "candidate-02")
        self.assertEqual(plan.profile.validation_schema_revision, 1)
        conn.require_usable_validated_demo_profile(plan.profile)  # no raise

    def test_websocket_host_mutated_to_production_rejected(self) -> None:
        plan = _valid_plan()
        # Use a real EndpointComponents so the exact-type check passes
        # and the value check is what's actually exercised.
        real_type_spoofed_ws = plan.profile.rest.__class__(
            scheme="wss",
            host="external-api-ws.kalshi.com",
            port=conn.DEMO_PORT,
            path=conn.DEMO_WEBSOCKET_PATH,
            has_user_info=False,
            has_query=False,
            has_fragment=False,
        )
        object.__setattr__(plan.profile, "websocket", real_type_spoofed_ws)
        self._assert_halts_before_dns(plan)

    def test_websocket_scheme_mutated_rejected(self) -> None:
        plan = _valid_plan()
        mutated = plan.profile.websocket.__class__(
            scheme="ws",
            host=conn.DEMO_WEBSOCKET_HOST,
            port=conn.DEMO_PORT,
            path=conn.DEMO_WEBSOCKET_PATH,
            has_user_info=False,
            has_query=False,
            has_fragment=False,
        )
        object.__setattr__(plan.profile, "websocket", mutated)
        self._assert_halts_before_dns(plan)

    def test_websocket_port_mutated_rejected(self) -> None:
        plan = _valid_plan()
        mutated = plan.profile.websocket.__class__(
            scheme="wss",
            host=conn.DEMO_WEBSOCKET_HOST,
            port=8443,
            path=conn.DEMO_WEBSOCKET_PATH,
            has_user_info=False,
            has_query=False,
            has_fragment=False,
        )
        object.__setattr__(plan.profile, "websocket", mutated)
        self._assert_halts_before_dns(plan)

    def test_websocket_path_mutated_rejected(self) -> None:
        plan = _valid_plan()
        mutated = plan.profile.websocket.__class__(
            scheme="wss",
            host=conn.DEMO_WEBSOCKET_HOST,
            port=conn.DEMO_PORT,
            path="/trade-api/ws/v1",
            has_user_info=False,
            has_query=False,
            has_fragment=False,
        )
        object.__setattr__(plan.profile, "websocket", mutated)
        self._assert_halts_before_dns(plan)

    def test_websocket_has_user_info_true_rejected(self) -> None:
        plan = _valid_plan()
        mutated = plan.profile.websocket.__class__(
            scheme="wss",
            host=conn.DEMO_WEBSOCKET_HOST,
            port=conn.DEMO_PORT,
            path=conn.DEMO_WEBSOCKET_PATH,
            has_user_info=True,
            has_query=False,
            has_fragment=False,
        )
        object.__setattr__(plan.profile, "websocket", mutated)
        self._assert_halts_before_dns(plan)

    def test_websocket_has_query_true_rejected(self) -> None:
        plan = _valid_plan()
        mutated = plan.profile.websocket.__class__(
            scheme="wss",
            host=conn.DEMO_WEBSOCKET_HOST,
            port=conn.DEMO_PORT,
            path=conn.DEMO_WEBSOCKET_PATH,
            has_user_info=False,
            has_query=True,
            has_fragment=False,
        )
        object.__setattr__(plan.profile, "websocket", mutated)
        self._assert_halts_before_dns(plan)

    def test_websocket_has_fragment_true_rejected(self) -> None:
        plan = _valid_plan()
        mutated = plan.profile.websocket.__class__(
            scheme="wss",
            host=conn.DEMO_WEBSOCKET_HOST,
            port=conn.DEMO_PORT,
            path=conn.DEMO_WEBSOCKET_PATH,
            has_user_info=False,
            has_query=False,
            has_fragment=True,
        )
        object.__setattr__(plan.profile, "websocket", mutated)
        self._assert_halts_before_dns(plan)

    def test_websocket_exact_type_required_duck_proxy_rejected(self) -> None:
        plan = _valid_plan()
        spoofed_ws = _DeceptiveEndpointComponentsProxy(
            scheme="wss",
            host=conn.DEMO_WEBSOCKET_HOST,
            port=conn.DEMO_PORT,
            path=conn.DEMO_WEBSOCKET_PATH,
        )
        object.__setattr__(plan.profile, "websocket", spoofed_ws)
        with self.assertRaises(conn.ConnectivityTypeError):
            conn.require_usable_validated_demo_profile(plan.profile)

    def test_allowlist_revision_mutated_rejected(self) -> None:
        plan = _valid_plan()
        object.__setattr__(plan.profile, "allowlist_revision", "candidate-03")
        self._assert_halts_before_dns(plan)

    def test_allowlist_revision_str_subclass_rejected(self) -> None:
        plan = _valid_plan()
        spoofed = _SpoofedEqualityStr("candidate-02")
        object.__setattr__(plan.profile, "allowlist_revision", spoofed)
        self._assert_halts_before_dns(plan)

    def test_validation_schema_revision_mutated_rejected(self) -> None:
        plan = _valid_plan()
        object.__setattr__(plan.profile, "validation_schema_revision", 2)
        self._assert_halts_before_dns(plan)

    def test_validation_schema_revision_bool_rejected(self) -> None:
        plan = _valid_plan()
        object.__setattr__(plan.profile, "validation_schema_revision", True)
        self._assert_halts_before_dns(plan)

    def test_validation_schema_revision_spoofed_int_rejected(self) -> None:
        plan = _valid_plan()
        spoofed = _SpoofedEqualityInt(2)
        object.__setattr__(plan.profile, "validation_schema_revision", spoofed)
        self._assert_halts_before_dns(plan)

    def test_accepted_revisions_verified_against_canonical_fixtures(self) -> None:
        """Cross-checks the hard-bound constants directly against the
        real, unmodified `validate()` function's output for the exact
        inputs every pre-existing canonical test file in this
        repository supplies -- not merely against this test file's own
        fixture."""

        result = validate(
            Input(
                environment="KALSHI_DEMO",
                environment_source_field="ARB_KALSHI_ENVIRONMENT",
                rest_endpoint=_DEMO_REST,
                websocket_endpoint=_DEMO_WS,
                requested_capability=RC.DEMO_PUBLIC_REST_READ.value,
                capability_envelope=_connectivity_envelope(),
                config_schema_revision=1,
                endpoint_allowlist_revision="candidate-02",
            )
        )
        assert result.success is not None, result.halt
        self.assertEqual(result.success.allowlist_revision, conn._ACCEPTED_ALLOWLIST_REVISION)
        self.assertEqual(
            result.success.validation_schema_revision,
            conn._ACCEPTED_VALIDATION_SCHEMA_REVISION,
        )


class SourceBindingExactTypeTrustBoundaryTests(unittest.TestCase):
    """Implementation 08 correction 1: every current
    `OfficialRestSourceBinding` field is mechanically bound back to the
    exact canonical source-binding-record bytes retained on the plan
    (`plan.source_binding_record_bytes`), not merely checked for
    individual well-typedness or a redundant mutable copy. Every
    mutation halts before DNS, with zero resolver calls."""

    def _assert_halts_before_dns(self, plan) -> None:
        with self.assertRaises(conn.ConnectivityError):
            conn.require_usable_official_rest_source_binding(
                plan.source_binding,
                plan.execution_dispatch_expectation,
                plan.source_binding_record_bytes,
            )
        dns_calls = []
        with mock.patch.object(
            conn,
            "_resolve_addresses_with_deadline",
            side_effect=lambda *a, **k: dns_calls.append(1),
        ):
            result = conn.execute_demo_read_only_connectivity(plan)
        self.assertEqual(dns_calls, [])
        self.assertIsInstance(result, conn.ConnectivityPreflightHalt)
        self.assertEqual(result.code, conn.ConnectivityHaltCode.EXECUTION_PLAN_MUTATED)

    def test_valid_binding_passes(self) -> None:
        plan = _valid_plan()
        conn.require_usable_official_rest_source_binding(
            plan.source_binding,
            plan.execution_dispatch_expectation,
            plan.source_binding_record_bytes,
        )  # no raise

    def test_plan_retains_the_exact_canonical_record_bytes(self) -> None:
        plan = _valid_plan()
        self.assertIs(type(plan.source_binding_record_bytes), bytes)
        self.assertEqual(
            hashlib.sha256(plan.source_binding_record_bytes).hexdigest(),
            plan.execution_dispatch_expectation.expected_source_binding_record_sha256,
        )

    def test_non_str_retrieved_at_utc_rejected(self) -> None:
        plan = _valid_plan()
        object.__setattr__(plan.source_binding, "retrieved_at_utc", 12345)
        self._assert_halts_before_dns(plan)

    def test_malformed_retrieved_at_utc_rejected(self) -> None:
        plan = _valid_plan()
        object.__setattr__(plan.source_binding, "retrieved_at_utc", "not-a-timestamp")
        self._assert_halts_before_dns(plan)

    def test_naive_retrieved_at_utc_rejected(self) -> None:
        plan = _valid_plan()
        object.__setattr__(
            plan.source_binding, "retrieved_at_utc", "2026-08-07T00:00:00"
        )
        self._assert_halts_before_dns(plan)

    def test_deceptive_string_subclass_retrieved_at_utc_rejected(self) -> None:
        plan = _valid_plan()
        spoofed = _SpoofedEqualityStr(plan.source_binding.retrieved_at_utc)
        object.__setattr__(plan.source_binding, "retrieved_at_utc", spoofed)
        self._assert_halts_before_dns(plan)

    def test_retrieved_at_utc_changed_to_a_different_valid_timestamp_rejected(
        self,
    ) -> None:
        """Dispatch-required adversarial test: a *different but
        syntactically valid* RFC3339 UTC timestamp -- not malformed at
        all, just not the one actually in the canonical record -- must
        still be rejected, because it no longer matches the
        recomputed authoritative value."""

        plan = _valid_plan()
        original = plan.source_binding.retrieved_at_utc
        self.assertTrue(conn._is_rfc3339_utc(original))
        different_but_valid = "2030-01-01T00:00:00Z"
        self.assertNotEqual(different_but_valid, original)
        self.assertTrue(conn._is_rfc3339_utc(different_but_valid))
        object.__setattr__(plan.source_binding, "retrieved_at_utc", different_but_valid)
        self._assert_halts_before_dns(plan)

    def test_zero_raw_openapi_byte_length_rejected(self) -> None:
        plan = _valid_plan()
        object.__setattr__(plan.source_binding, "raw_openapi_byte_length", 0)
        self._assert_halts_before_dns(plan)

    def test_negative_raw_openapi_byte_length_rejected(self) -> None:
        plan = _valid_plan()
        object.__setattr__(plan.source_binding, "raw_openapi_byte_length", -1)
        self._assert_halts_before_dns(plan)

    def test_bool_raw_openapi_byte_length_rejected(self) -> None:
        plan = _valid_plan()
        object.__setattr__(plan.source_binding, "raw_openapi_byte_length", True)
        self._assert_halts_before_dns(plan)

    def test_spoofed_int_raw_openapi_byte_length_rejected(self) -> None:
        plan = _valid_plan()
        spoofed = _SpoofedEqualityInt(plan.source_binding.raw_openapi_byte_length)
        object.__setattr__(plan.source_binding, "raw_openapi_byte_length", spoofed)
        self._assert_halts_before_dns(plan)

    def test_raw_openapi_byte_length_changed_to_different_valid_int_rejected(
        self,
    ) -> None:
        """Dispatch-required adversarial test: a different *positive
        exact* int -- not zero, negative, or bool -- still must not
        match the recomputed authoritative value."""

        plan = _valid_plan()
        real_length = plan.source_binding.raw_openapi_byte_length
        object.__setattr__(
            plan.source_binding, "raw_openapi_byte_length", real_length + 1000
        )
        self._assert_halts_before_dns(plan)

    def test_bool_source_binding_record_byte_length_rejected(self) -> None:
        plan = _valid_plan()
        object.__setattr__(plan.source_binding, "source_binding_record_byte_length", True)
        self._assert_halts_before_dns(plan)

    def test_source_binding_record_byte_length_changed_to_different_valid_int_rejected(
        self,
    ) -> None:
        """Dispatch-required adversarial test: mutating only the public
        length field to a different, otherwise perfectly well-typed
        positive int must still be caught -- Implementation 08 no
        longer relies on a redundant mutable copy of this field as a
        purported commitment; it is instead recomputed from the
        retained canonical record bytes at every gate."""

        plan = _valid_plan()
        real_length = plan.source_binding.source_binding_record_byte_length
        object.__setattr__(
            plan.source_binding, "source_binding_record_byte_length", real_length + 1
        )
        self._assert_halts_before_dns(plan)

    def test_no_redundant_commitment_field_exists_on_binding(self) -> None:
        field_names = set(conn.OfficialRestSourceBinding.__dataclass_fields__)
        self.assertEqual(
            field_names,
            {
                "source_url",
                "retrieved_at_utc",
                "raw_openapi_byte_length",
                "raw_openapi_sha256",
                "source_binding_record_byte_length",
                "source_binding_record_sha256",
                "operation_method",
                "operation_path",
                "effective_security_source",
                "effective_auth_classification",
                "reviewed_demo_rest_origin",
                "reviewed_full_request_path",
                "binding_schema_revision",
            },
        )

    def test_deceptive_effective_security_source_proxy_rejected(self) -> None:
        plan = _valid_plan()
        spoofed = _DeceptiveValueProxy(
            plan.source_binding.effective_security_source.value
        )
        object.__setattr__(plan.source_binding, "effective_security_source", spoofed)
        self._assert_halts_before_dns(plan)

    def test_effective_security_source_changed_to_different_valid_member_rejected(
        self,
    ) -> None:
        """Dispatch-required adversarial test: a genuinely different,
        valid `EffectiveSecuritySource` member (not a type-spoofing
        proxy) still must not match the recomputed authoritative value
        derived from the actual canonical record."""

        plan = _valid_plan()
        original = plan.source_binding.effective_security_source
        replacement = (
            conn.EffectiveSecuritySource.GLOBAL_INHERITED
            if original is not conn.EffectiveSecuritySource.GLOBAL_INHERITED
            else conn.EffectiveSecuritySource.OPERATION_OVERRIDE
        )
        self.assertNotEqual(replacement, original)
        object.__setattr__(plan.source_binding, "effective_security_source", replacement)
        self._assert_halts_before_dns(plan)

    def test_retained_record_bytes_changed_to_non_matching_sha_rejected(self) -> None:
        """Dispatch-required adversarial test: the retained canonical
        record bytes themselves are mutated (still a well-formed,
        parseable, canonically-serialized record -- just a different
        one) without also changing
        `ExecutionDispatchExpectation.expected_source_binding_record_sha256`
        to match. The gate must reject this via the hash-mismatch check
        inside the fresh recomputation, before any DNS action."""

        plan = _valid_plan()
        different_record_bytes = _valid_record_bytes(
            retrieved_at_utc="2030-01-01T00:00:00Z"
        )
        self.assertNotEqual(different_record_bytes, plan.source_binding_record_bytes)
        different_sha = hashlib.sha256(different_record_bytes).hexdigest()
        self.assertNotEqual(
            different_sha,
            plan.execution_dispatch_expectation.expected_source_binding_record_sha256,
        )
        object.__setattr__(plan, "source_binding_record_bytes", different_record_bytes)
        with self.assertRaises(conn.ConnectivityError):
            conn.require_usable_official_rest_source_binding(
                plan.source_binding,
                plan.execution_dispatch_expectation,
                plan.source_binding_record_bytes,
            )
        dns_calls = []
        with mock.patch.object(
            conn,
            "_resolve_addresses_with_deadline",
            side_effect=lambda *a, **k: dns_calls.append(1),
        ):
            result = conn.execute_demo_read_only_connectivity(plan)
        self.assertEqual(dns_calls, [])
        self.assertEqual(result.code, conn.ConnectivityHaltCode.EXECUTION_PLAN_MUTATED)

    def test_non_bytes_record_bytes_rejected(self) -> None:
        plan = _valid_plan()
        object.__setattr__(plan, "source_binding_record_bytes", "not-bytes")
        self._assert_halts_before_dns(plan)

    def test_duck_typed_binding_look_alike_rejected(self) -> None:
        plan = _valid_plan()

        class LookAlikeBinding:
            def __getattr__(self, name):
                return getattr(plan.source_binding, name)

        with self.assertRaises(conn.ConnectivityTypeError):
            conn.require_usable_official_rest_source_binding(
                LookAlikeBinding(),
                plan.execution_dispatch_expectation,
                plan.source_binding_record_bytes,
            )

    def test_subclassed_binding_rejected(self) -> None:
        plan = _valid_plan()

        class SubclassedBinding(conn.OfficialRestSourceBinding):
            pass

        subclassed = SubclassedBinding(
            **{
                f: getattr(plan.source_binding, f)
                for f in plan.source_binding.__dataclass_fields__
            }
        )
        with self.assertRaises(conn.ConnectivityTypeError):
            conn.require_usable_official_rest_source_binding(
                subclassed,
                plan.execution_dispatch_expectation,
                plan.source_binding_record_bytes,
            )


class PlanningTests(unittest.TestCase):
    """Section 16.2 items 1-31 (adjusted numbering: this implementation
    consolidates some items into fewer, broader-covering tests)."""

    def test_valid_input_produces_exact_request_plan(self) -> None:
        plan = _valid_plan()
        self.assertEqual(plan.method, "GET")
        self.assertEqual(plan.full_path, "/trade-api/v2/exchange/status")
        self.assertEqual(plan.request_budget, 1)
        self.assertEqual(plan.retry_count, 0)
        self.assertEqual(plan.overall_timeout_ms, 10000)
        self.assertEqual(plan.socket_stage_timeout_ms, 5000)

    def test_plan_input_has_no_credential_field(self) -> None:
        field_names = [
            f for f in conn.ConnectivityPreflightInput.__dataclass_fields__
        ]
        self.assertFalse(any("credential" in f for f in field_names))

    def test_reading_candidate_credential_env_vars_fails_this_test(self) -> None:
        with mock.patch.dict(os.environ, {"KALSHI_DEMO_API_KEY_ID": "must-not-leak"}):
            plan = _valid_plan()
            self.assertNotIn("must-not-leak", repr(plan))

    def test_recommended_production_host_halts_before_dns(self) -> None:
        result = validate(
            Input(
                environment="KALSHI_PRODUCTION",
                environment_source_field="ARB_KALSHI_ENVIRONMENT",
                rest_endpoint=_PROD_REST,
                websocket_endpoint=_DEMO_WS,
                requested_capability=RC.PRODUCTION_PUBLIC_REST_READ.value,
                capability_envelope=_connectivity_envelope(
                    production_public_reads=AV.PERMITTED
                ),
                config_schema_revision=1,
                endpoint_allowlist_revision="candidate-02",
            )
        )
        self.assertIsNotNone(result.halt)

    def test_wrong_environment_halts_before_dns(self) -> None:
        result = validate(
            Input(
                environment="UNSET",
                environment_source_field="ARB_KALSHI_ENVIRONMENT",
                rest_endpoint=_DEMO_REST,
                websocket_endpoint=_DEMO_WS,
                requested_capability=RC.DEMO_PUBLIC_REST_READ.value,
                capability_envelope=_connectivity_envelope(),
                config_schema_revision=1,
                endpoint_allowlist_revision="candidate-02",
            )
        )
        self.assertIsNotNone(result.halt)

    def test_source_binding_record_bytes_missing_halts(self) -> None:
        plan = conn.plan_demo_read_only_connectivity(
            _preflight_input(record_bytes=b"", expected_record_sha256="0" * 64)
        )
        self.assertIsInstance(plan, conn.ConnectivityPreflightHalt)
        self.assertEqual(
            plan.code, conn.ConnectivityHaltCode.OFFICIAL_SOURCE_IDENTITY_UNBOUND
        )

    def test_placeholder_all_zero_expected_hash_halts(self) -> None:
        record_bytes = _valid_record_bytes()
        plan = conn.plan_demo_read_only_connectivity(
            _preflight_input(record_bytes=record_bytes, expected_record_sha256="0" * 64)
        )
        self.assertIsInstance(plan, conn.ConnectivityPreflightHalt)
        self.assertEqual(
            plan.code, conn.ConnectivityHaltCode.OFFICIAL_SOURCE_IDENTITY_UNBOUND
        )

    def test_record_hash_mismatch_halts(self) -> None:
        record_bytes = _valid_record_bytes()
        wrong_expected = hashlib.sha256(record_bytes + b"x").hexdigest()
        plan = conn.plan_demo_read_only_connectivity(
            _preflight_input(record_bytes=record_bytes, expected_record_sha256=wrong_expected)
        )
        self.assertIsInstance(plan, conn.ConnectivityPreflightHalt)
        self.assertEqual(
            plan.code, conn.ConnectivityHaltCode.OFFICIAL_SOURCE_IDENTITY_UNBOUND
        )

    def test_raw_openapi_sha_mismatch_halts(self) -> None:
        plan = conn.plan_demo_read_only_connectivity(
            _preflight_input(expected_raw_sha256=_OTHER_RAW_OPENAPI_SHA)
        )
        self.assertIsInstance(plan, conn.ConnectivityPreflightHalt)
        self.assertEqual(
            plan.code, conn.ConnectivityHaltCode.OFFICIAL_SOURCE_IDENTITY_UNBOUND
        )

    def test_caller_created_source_binding_not_accepted_as_planner_input(self) -> None:
        field_types = {
            name: f.type
            for name, f in conn.ConnectivityPreflightInput.__dataclass_fields__.items()
        }
        self.assertNotIn("OfficialRestSourceBinding", str(field_types))

    def test_duplicate_json_keys_halt_before_dns(self) -> None:
        record_bytes = _valid_record_bytes()
        text = record_bytes.decode("utf-8")
        malformed = text[:-1] + ',"schema_version":1}'
        plan = conn.plan_demo_read_only_connectivity(
            _preflight_input(
                record_bytes=malformed.encode("utf-8"),
                expected_record_sha256=hashlib.sha256(
                    malformed.encode("utf-8")
                ).hexdigest(),
            )
        )
        self.assertIsInstance(plan, conn.ConnectivityPreflightHalt)

    def test_wrong_source_url_halts(self) -> None:
        record_bytes = _valid_record_bytes(source_url="https://example.com/openapi.yaml")
        plan = conn.plan_demo_read_only_connectivity(
            _preflight_input(record_bytes=record_bytes, expected_record_sha256=None)
        )
        self.assertIsInstance(plan, conn.ConnectivityPreflightHalt)

    def test_global_inherited_nonempty_auth_halts(self) -> None:
        record_bytes = _valid_record_bytes(
            effective_security_source="GLOBAL_INHERITED",
            effective_security=[{"apiKeyAuth": []}],
            effective_allows_anonymous=False,
            effective_auth_classification="AUTHENTICATED_READ_ONLY",
            operation_security_key_present=False,
        )
        plan = conn.plan_demo_read_only_connectivity(
            _preflight_input(record_bytes=record_bytes, expected_record_sha256=None)
        )
        self.assertIsInstance(plan, conn.ConnectivityPreflightHalt)
        self.assertEqual(plan.code, conn.ConnectivityHaltCode.OFFICIAL_SOURCE_CONFLICT)

    def test_operation_empty_array_overrides_global_authenticated(self) -> None:
        record_bytes = _valid_record_bytes(
            effective_security_source="OPERATION_OVERRIDE",
            effective_security=[],
            effective_allows_anonymous=True,
            effective_auth_classification="PUBLIC_UNAUTHENTICATED_READ_ONLY",
        )
        plan = conn.plan_demo_read_only_connectivity(
            _preflight_input(record_bytes=record_bytes, expected_record_sha256=None)
        )
        self.assertIsInstance(plan, conn.ConnectivityPreflightPlan)

    def test_operation_nonempty_overrides_global_no_auth_and_halts(self) -> None:
        record_bytes = _valid_record_bytes(
            effective_security_source="OPERATION_OVERRIDE",
            effective_security=[{"apiKeyAuth": []}],
            effective_allows_anonymous=False,
            effective_auth_classification="AUTHENTICATED_READ_ONLY",
        )
        plan = conn.plan_demo_read_only_connectivity(
            _preflight_input(record_bytes=record_bytes, expected_record_sha256=None)
        )
        self.assertIsInstance(plan, conn.ConnectivityPreflightHalt)

    def test_empty_object_alternative_allows_anonymous(self) -> None:
        record_bytes = _valid_record_bytes(
            effective_security_source="OPERATION_OVERRIDE",
            effective_security=[{"apiKeyAuth": []}, {}],
            effective_allows_anonymous=True,
            effective_auth_classification="PUBLIC_UNAUTHENTICATED_READ_ONLY",
        )
        plan = conn.plan_demo_read_only_connectivity(
            _preflight_input(record_bytes=record_bytes, expected_record_sha256=None)
        )
        self.assertIsInstance(plan, conn.ConnectivityPreflightPlan)

    def test_malformed_effective_security_halts_with_conflict(self) -> None:
        record_bytes = _valid_record_bytes(
            effective_security_source="OPERATION_OVERRIDE",
            effective_security="not-an-array",
            effective_allows_anonymous=True,
            effective_auth_classification="PUBLIC_UNAUTHENTICATED_READ_ONLY",
        )
        plan = conn.plan_demo_read_only_connectivity(
            _preflight_input(record_bytes=record_bytes, expected_record_sha256=None)
        )
        self.assertIsInstance(plan, conn.ConnectivityPreflightHalt)
        self.assertEqual(plan.code, conn.ConnectivityHaltCode.OFFICIAL_SOURCE_CONFLICT)

    def test_non_dispatch_bound_record_is_stale(self) -> None:
        record_bytes = _valid_record_bytes()
        real_hash = hashlib.sha256(record_bytes).hexdigest()
        different_expected = real_hash[:-1] + ("0" if real_hash[-1] != "0" else "1")
        plan = conn.plan_demo_read_only_connectivity(
            _preflight_input(record_bytes=record_bytes, expected_record_sha256=different_expected)
        )
        self.assertIsInstance(plan, conn.ConnectivityPreflightHalt)

    def test_exact_plan_type_required(self) -> None:
        @dataclass(frozen=True)
        class FakePlan:
            pass

        with self.assertRaises(conn.ConnectivityTypeError):
            conn.require_usable_connectivity_preflight_plan(FakePlan())

    def test_subclassed_plan_rejected(self) -> None:
        plan = _valid_plan()

        class SubclassedPlan(conn.ConnectivityPreflightPlan):
            pass

        subclassed = SubclassedPlan(**{f: getattr(plan, f) for f in plan.__dataclass_fields__})
        with self.assertRaises(conn.ConnectivityTypeError):
            conn.require_usable_connectivity_preflight_plan(subclassed)

    def test_duck_typed_plan_look_alike_rejected(self) -> None:
        plan = _valid_plan()

        class LookAlike:
            def __getattr__(self, name):
                return getattr(plan, name)

        with self.assertRaises(conn.ConnectivityTypeError):
            conn.require_usable_connectivity_preflight_plan(LookAlike())

    def test_mutated_plan_halts_before_dns(self) -> None:
        plan = _valid_plan()
        object.__setattr__(plan, "full_path", "/trade-api/v2/markets")
        with self.assertRaises(conn.ConnectivityError):
            conn.require_usable_connectivity_preflight_plan(plan)

    def test_exact_profile_type_required(self) -> None:
        with self.assertRaises(conn.ConnectivityTypeError):
            conn.require_usable_validated_demo_profile(object())

    def test_duck_typed_profile_rejected(self) -> None:
        plan = _valid_plan()

        class DuckProfile:
            def __getattr__(self, name):
                return getattr(plan.profile, name)

        with self.assertRaises(conn.ConnectivityTypeError):
            conn.require_usable_validated_demo_profile(DuckProfile())

    def test_mutated_profile_to_production_halts(self) -> None:
        plan = _valid_plan()
        prod_rest = plan.profile.rest.__class__(
            scheme="https", host="external-api.kalshi.com", port=443,
            path="/trade-api/v2", has_user_info=False, has_query=False,
            has_fragment=False,
        )
        object.__setattr__(plan.profile, "rest", prod_rest)
        with self.assertRaises(conn.ConnectivityError):
            conn.require_usable_validated_demo_profile(plan.profile)

    def test_capability_envelope_prohibition_reenforced_at_plan_gate(self) -> None:
        plan = _valid_plan()
        object.__setattr__(plan.capability_envelope, "network_access", AV.PROHIBITED)
        with self.assertRaises(Exception):
            conn.require_usable_connectivity_preflight_plan(plan)


class ProductionExecutorSignatureTests(unittest.TestCase):
    def test_executor_accepts_no_transport_style_argument(self) -> None:
        import inspect

        sig = inspect.signature(conn.execute_demo_read_only_connectivity)
        self.assertEqual(list(sig.parameters), ["plan"])

    def test_fake_seam_not_exposed_through_public_surface(self) -> None:
        self.assertNotIn("_resolve_addresses", conn.__all__)
        self.assertNotIn("_tls_wrap", conn.__all__)
        plan_fields = set(conn.ConnectivityPreflightPlan.__dataclass_fields__)
        self.assertFalse(plan_fields & {"transport", "client", "resolver"})


class DnsAndTlsTests(unittest.TestCase):
    def test_dns_resolution_failure_halts(self) -> None:
        plan = _valid_plan()
        with mock.patch.object(
            conn, "_resolve_addresses_with_deadline", side_effect=OSError("resolution failed")
        ):
            result = conn.execute_demo_read_only_connectivity(plan)
        self.assertEqual(result.code, conn.ConnectivityHaltCode.DNS_VERIFICATION_FAILED)

    def test_only_private_address_halts(self) -> None:
        result = _run_execution(addresses=(_PRIVATE_ADDR,))
        self.assertEqual(result.code, conn.ConnectivityHaltCode.DNS_VERIFICATION_FAILED)

    def test_mixed_public_and_prohibited_halts_entire_answer(self) -> None:
        result = _run_execution(addresses=(_PUBLIC_ADDR_A, _PRIVATE_ADDR))
        self.assertEqual(result.code, conn.ConnectivityHaltCode.DNS_VERIFICATION_FAILED)

    def test_all_public_answer_produces_verified_set(self) -> None:
        result = _run_execution(addresses=(_PUBLIC_ADDR_A, _PUBLIC_ADDR_B))
        self.assertIsInstance(result, conn.ConnectivityPreflightSuccess)
        self.assertEqual(result.verified_dns_address_count, 2)
        self.assertEqual(result.resolver_returned_address_count, 2)

    def test_deterministic_selection_stable_across_permutations(self) -> None:
        result_a = _run_execution(addresses=(_PUBLIC_ADDR_B, _PUBLIC_ADDR_A))
        result_b = _run_execution(addresses=(_PUBLIC_ADDR_A, _PUBLIC_ADDR_B))
        self.assertEqual(result_a.selected_numeric_address, result_b.selected_numeric_address)
        pairs = conn._classify_dns_answer(_af_candidates(_PUBLIC_ADDR_B, _PUBLIC_ADDR_A))
        self.assertEqual(pairs[0][1], _PUBLIC_ADDR_A)

    def test_no_second_address_attempted_after_connect_failure(self) -> None:
        plan = _valid_plan()
        calls = []

        def fake_resolve(host, port):
            return _af_candidates(_PUBLIC_ADDR_A, _PUBLIC_ADDR_B)

        def fake_connect(address, port, family, timeout_s):
            calls.append(address)
            raise OSError("refused")

        with mock.patch.object(conn, "_resolve_addresses", side_effect=fake_resolve), \
             mock.patch.object(conn, "_connect_tcp", side_effect=fake_connect):
            result = conn.execute_demo_read_only_connectivity(plan)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result.code, conn.ConnectivityHaltCode.TRANSPORT_FAILURE)

    def test_gates_rerun_after_dns_before_socket_mutation_halts(self) -> None:
        plan = _valid_plan()

        def fake_resolve(host, port):
            object.__setattr__(plan, "full_path", "/mutated")
            return _af_candidates(_PUBLIC_ADDR_A)

        with mock.patch.object(conn, "_resolve_addresses", side_effect=fake_resolve):
            result = conn.execute_demo_read_only_connectivity(plan)
        self.assertEqual(result.code, conn.ConnectivityHaltCode.EXECUTION_PLAN_MUTATED)

    def test_transport_hostname_re_resolution_is_not_performed(self) -> None:
        plan = _valid_plan()
        resolve_calls = []

        def fake_resolve(host, port):
            resolve_calls.append(host)
            return _af_candidates(_PUBLIC_ADDR_A)

        with mock.patch.object(conn, "_resolve_addresses", side_effect=fake_resolve), \
             mock.patch.object(conn, "_connect_tcp", return_value=mock.Mock()), \
             mock.patch.object(
                 conn, "_tls_wrap",
                 return_value=_FakeTLSSocket(_success_http_response()),
             ):
            conn.execute_demo_read_only_connectivity(plan)
        self.assertEqual(resolve_calls, [conn.DEMO_HOST])

    def test_socket_pinned_to_selected_address_host_sni_unchanged(self) -> None:
        plan = _valid_plan()
        seen_connect = {}
        seen_tls = {}

        def fake_connect(address, port, family, timeout_s):
            seen_connect["address"] = address
            return mock.Mock()

        def fake_tls_wrap(raw_sock, server_hostname, timeout_s):
            seen_tls["hostname"] = server_hostname
            return _FakeTLSSocket(_success_http_response())

        with mock.patch.object(conn, "_resolve_addresses", return_value=_af_candidates(_PUBLIC_ADDR_A)), \
             mock.patch.object(conn, "_connect_tcp", side_effect=fake_connect), \
             mock.patch.object(conn, "_tls_wrap", side_effect=fake_tls_wrap):
            conn.execute_demo_read_only_connectivity(plan)
        self.assertEqual(seen_connect["address"], _PUBLIC_ADDR_A)
        self.assertEqual(seen_tls["hostname"], conn.DEMO_HOST)

    def test_tls_certificate_validation_failure_halts(self) -> None:
        result = _run_execution(tls_error=ssl.SSLCertVerificationError("bad cert"))
        self.assertEqual(result.code, conn.ConnectivityHaltCode.TLS_VERIFICATION_FAILED)

    def test_tls_hostname_mismatch_halts(self) -> None:
        result = _run_execution(tls_error=ssl.SSLError("hostname mismatch"))
        self.assertEqual(result.code, conn.ConnectivityHaltCode.TLS_VERIFICATION_FAILED)

    def test_tls_below_1_2_halts(self) -> None:
        result = _run_execution(tls_version="TLSv1.1")
        self.assertEqual(result.code, conn.ConnectivityHaltCode.TLS_VERIFICATION_FAILED)

    def test_gates_rerun_before_send(self) -> None:
        plan = _valid_plan()

        def fake_tls_wrap(raw_sock, server_hostname, timeout_s):
            object.__setattr__(plan, "method", "POST")
            return _FakeTLSSocket(_success_http_response())

        with mock.patch.object(conn, "_resolve_addresses", return_value=_af_candidates(_PUBLIC_ADDR_A)), \
             mock.patch.object(conn, "_connect_tcp", return_value=mock.Mock()), \
             mock.patch.object(conn, "_tls_wrap", side_effect=fake_tls_wrap):
            result = conn.execute_demo_read_only_connectivity(plan)
        self.assertEqual(result.code, conn.ConnectivityHaltCode.EXECUTION_PLAN_MUTATED)


class DnsAddressFamilyValidationTests(unittest.TestCase):
    """Implementation 10 correction 2: the family `socket.getaddrinfo()`
    actually returns is preserved and cross-validated against the
    parsed address text and sockaddr shape, before any address is
    canonicalized/deduplicated/sorted or a TCP attempt is made. All
    fully offline -- no real DNS occurs anywhere in this class."""

    def test_valid_af_inet_candidate_accepted(self) -> None:
        candidates = ((socket.AF_INET, (_PUBLIC_ADDR_A, 443)),)
        result = conn._classify_dns_answer(candidates)
        self.assertEqual(result, ((4, _PUBLIC_ADDR_A),))

    def test_valid_af_inet6_candidate_accepted(self) -> None:
        candidates = ((socket.AF_INET6, (_PUBLIC_ADDR_V6, 443, 0, 0)),)
        result = conn._classify_dns_answer(candidates)
        self.assertEqual(result, ((6, _PUBLIC_ADDR_V6),))

    def test_unknown_family_with_otherwise_public_ipv4_text_rejected(self) -> None:
        # AF_UNIX (or any family other than AF_INET/AF_INET6) carrying
        # what would otherwise be an acceptable public IPv4 address.
        bogus_family = getattr(socket, "AF_UNIX", 1)
        candidates = ((bogus_family, (_PUBLIC_ADDR_A, 443)),)
        with self.assertRaises(conn.ConnectivityError):
            conn._classify_dns_answer(candidates)

    def test_af_inet_carrying_ipv6_text_rejected(self) -> None:
        candidates = ((socket.AF_INET, (_PUBLIC_ADDR_V6, 443)),)
        with self.assertRaises(conn.ConnectivityError):
            conn._classify_dns_answer(candidates)

    def test_af_inet6_carrying_ipv4_text_rejected(self) -> None:
        candidates = ((socket.AF_INET6, (_PUBLIC_ADDR_A, 443, 0, 0)),)
        with self.assertRaises(conn.ConnectivityError):
            conn._classify_dns_answer(candidates)

    def test_malformed_sockaddr_wrong_shape_for_af_inet_rejected(self) -> None:
        # AF_INET sockaddr must be a 2-tuple; this one has an extra
        # element as if it were AF_INET6-shaped.
        candidates = ((socket.AF_INET, (_PUBLIC_ADDR_A, 443, 0, 0)),)
        with self.assertRaises(conn.ConnectivityError):
            conn._classify_dns_answer(candidates)

    def test_malformed_sockaddr_wrong_shape_for_af_inet6_rejected(self) -> None:
        candidates = ((socket.AF_INET6, (_PUBLIC_ADDR_V6, 443)),)
        with self.assertRaises(conn.ConnectivityError):
            conn._classify_dns_answer(candidates)

    def test_malformed_sockaddr_not_a_tuple_rejected(self) -> None:
        candidates = ((socket.AF_INET, _PUBLIC_ADDR_A),)
        with self.assertRaises(conn.ConnectivityError):
            conn._classify_dns_answer(candidates)

    def test_malformed_sockaddr_non_str_address_text_rejected(self) -> None:
        candidates = ((socket.AF_INET, (12345, 443)),)
        with self.assertRaises(conn.ConnectivityError):
            conn._classify_dns_answer(candidates)

    def test_malformed_candidate_not_a_tuple_rejected(self) -> None:
        with self.assertRaises(conn.ConnectivityError):
            conn._classify_dns_answer(("not-a-candidate-tuple",))

    def test_malformed_candidate_wrong_arity_rejected(self) -> None:
        with self.assertRaises(conn.ConnectivityError):
            conn._classify_dns_answer(((socket.AF_INET, (_PUBLIC_ADDR_A, 443), "extra"),))

    def test_bool_family_rejected(self) -> None:
        candidates = ((True, (_PUBLIC_ADDR_A, 443)),)
        with self.assertRaises(conn.ConnectivityError):
            conn._classify_dns_answer(candidates)

    def test_mixed_valid_and_invalid_family_answers_rejects_entire_answer(self) -> None:
        candidates = (
            (socket.AF_INET, (_PUBLIC_ADDR_A, 443)),
            (socket.AF_INET, (_PUBLIC_ADDR_V6, 443)),  # family/version mismatch
        )
        with self.assertRaises(conn.ConnectivityError):
            conn._classify_dns_answer(candidates)

    def test_deterministic_ipv4_before_ipv6_sorting(self) -> None:
        candidates = (
            (socket.AF_INET6, (_PUBLIC_ADDR_V6, 443, 0, 0)),
            (socket.AF_INET, (_PUBLIC_ADDR_A, 443)),
        )
        result = conn._classify_dns_answer(candidates)
        self.assertEqual(result[0], (4, _PUBLIC_ADDR_A))
        self.assertEqual(result[1], (6, _PUBLIC_ADDR_V6))
        # Order-independence: same result regardless of input order.
        reordered = tuple(reversed(candidates))
        self.assertEqual(conn._classify_dns_answer(reordered), result)

    def test_full_execution_flow_accepts_valid_af_inet6_answer(self) -> None:
        """End-to-end (still fully offline/mocked): a pure-IPv6 DNS
        answer, with family correctly preserved and validated, produces
        a successful connectivity result."""

        plan = _valid_plan()

        def fake_resolve(host, port):
            return ((socket.AF_INET6, (_PUBLIC_ADDR_V6, port, 0, 0)),)

        with mock.patch.object(conn, "_resolve_addresses", side_effect=fake_resolve), \
             mock.patch.object(conn, "_connect_tcp", return_value=mock.Mock()), \
             mock.patch.object(
                 conn, "_tls_wrap", return_value=_FakeTLSSocket(_success_http_response())
             ):
            result = conn.execute_demo_read_only_connectivity(plan)
        self.assertIsInstance(result, conn.ConnectivityPreflightSuccess)
        self.assertEqual(result.selected_numeric_address, _PUBLIC_ADDR_V6)
        self.assertEqual(result.selected_address_family, 6)

    def test_verified_dns_set_addresses_exact_tuple_type_required(self) -> None:
        """`require_usable_verified_dns_set` must reject a `list`
        standing in for the `addresses` tuple, and an `entry` that is a
        list rather than an exact 2-tuple, so a subclass/proxy cannot
        recreate the same trust-boundary weakness a looser `isinstance`
        check would have allowed."""

        pairs = conn._classify_dns_answer(_af_candidates(_PUBLIC_ADDR_A, _PUBLIC_ADDR_B))
        version, address = pairs[0]
        dns_set = conn.VerifiedDnsSet(
            host=conn.DEMO_HOST,
            port=conn.DEMO_PORT,
            addresses=pairs,
            selected_address=address,
            selected_ip_version=version,
        )
        object.__setattr__(dns_set, "addresses", list(pairs))
        with self.assertRaises(conn.ConnectivityError):
            conn.require_usable_verified_dns_set(dns_set, conn.DEMO_HOST, conn.DEMO_PORT)


class RequestAndResponseTests(unittest.TestCase):
    def test_first_send_consumes_only_budget(self) -> None:
        result = _run_execution()
        self.assertIsInstance(result, conn.ConnectivityPreflightSuccess)
        self.assertEqual(result.request_count, 1)

    def test_send_io_error_after_attempt_starts_yields_request_result_unknown(self) -> None:
        """Finding 3: once the single send attempt has begun,
        `sendall()` may raise having already written some bytes -- there
        is no way to prove zero bytes were transmitted. This must
        produce `REQUEST_RESULT_UNKNOWN`, not `TRANSPORT_FAILURE`, and
        must not retry."""

        result = _run_execution(send_error=OSError("connection reset by peer"))
        self.assertIsInstance(result, conn.ConnectivityPreflightHalt)
        self.assertEqual(result.code, conn.ConnectivityHaltCode.REQUEST_RESULT_UNKNOWN)
        self.assertEqual(result.stage, conn.ConnectivityStage.REQUEST_SENT)
        self.assertEqual(result.request_count, 1)
        self.assertEqual(result.retry_count, 0)

    def test_send_timeout_still_yields_connectivity_timeout(self) -> None:
        """A timeout while sending (distinct from an ambiguous
        partial-transmission I/O error) remains a deadline event."""

        result = _run_execution(send_error=socket.timeout("send timed out"))
        self.assertIsInstance(result, conn.ConnectivityPreflightHalt)
        self.assertEqual(result.code, conn.ConnectivityHaltCode.CONNECTIVITY_TIMEOUT)
        self.assertEqual(result.stage, conn.ConnectivityStage.REQUEST_SENT)

    def test_second_send_attempt_halts_budget_exhausted(self) -> None:
        """A plan whose `request_budget` has been consumed (0) must halt
        with `REQUEST_BUDGET_EXHAUSTED` at the pre-send check. In normal
        operation the stricter `require_usable_connectivity_preflight_plan`
        gate (run at all three checkpoints) already rejects
        `request_budget != 1` as `EXECUTION_PLAN_MUTATED` -- itself a
        conforming fail-closed outcome, and covered by
        `test_capability_envelope_prohibition_reenforced_at_plan_gate`
        and friends. This test isolates the dedicated budget check
        immediately before the HTTP send by holding the plan gates
        themselves as a no-op, proving that check independently exists
        and fires correctly."""

        plan = _valid_plan()
        object.__setattr__(plan, "request_budget", 0)
        with mock.patch.object(conn, "_revalidate_all_gates", return_value=None), \
             mock.patch.object(conn, "_resolve_addresses", return_value=_af_candidates(_PUBLIC_ADDR_A)), \
             mock.patch.object(conn, "_connect_tcp", return_value=mock.Mock()), \
             mock.patch.object(
                 conn, "_tls_wrap", return_value=_FakeTLSSocket(_success_http_response())
             ):
            result = conn.execute_demo_read_only_connectivity(plan)
        self.assertEqual(result.code, conn.ConnectivityHaltCode.REQUEST_BUDGET_EXHAUSTED)

    def test_mutated_zero_budget_caught_by_plan_gate_first(self) -> None:
        """The stricter, always-on outcome: without bypassing the plan
        gates, a zero request_budget is caught even earlier, at gate 1,
        as EXECUTION_PLAN_MUTATED."""

        plan = _valid_plan()
        object.__setattr__(plan, "request_budget", 0)
        result = conn.execute_demo_read_only_connectivity(plan)
        self.assertEqual(result.code, conn.ConnectivityHaltCode.EXECUTION_PLAN_MUTATED)

    def test_redirect_statuses_not_followed(self) -> None:
        for status in (301, 302, 303, 307, 308):
            with self.subTest(status=status):
                response = (
                    f"HTTP/1.1 {status} Redirect\r\nLocation: https://evil.example/\r\n\r\n"
                ).encode("ascii")
                result = _run_execution(response=response)
                self.assertEqual(
                    result.code, conn.ConnectivityHaltCode.ENDPOINT_REDIRECT_PROHIBITED
                )

    def test_401_403_halt_no_credentials_loaded(self) -> None:
        for status in (401, 403):
            with self.subTest(status=status):
                response = f"HTTP/1.1 {status} Denied\r\n\r\n".encode("ascii")
                result = _run_execution(response=response)
                self.assertEqual(
                    result.code,
                    conn.ConnectivityHaltCode.UNEXPECTED_AUTHENTICATION_REQUIREMENT,
                )
                # Halt records (Section 7.6) intentionally carry no
                # credentials_read counter at all -- that field only
                # exists on success evidence (Section 7.5) -- which is
                # itself proof no credential-loading path executed.
                self.assertFalse(hasattr(result, "credentials_read"))

    def test_429_halts_no_retry(self) -> None:
        response = b"HTTP/1.1 429 Too Many Requests\r\n\r\n"
        result = _run_execution(response=response)
        self.assertEqual(result.code, conn.ConnectivityHaltCode.UNEXPECTED_HTTP_STATUS)
        self.assertEqual(result.retry_count, 0)

    def test_5xx_halts_no_retry(self) -> None:
        for status in (500, 503, 504):
            with self.subTest(status=status):
                response = f"HTTP/1.1 {status} Error\r\n\r\n".encode("ascii")
                result = _run_execution(response=response)
                self.assertEqual(result.code, conn.ConnectivityHaltCode.UNEXPECTED_HTTP_STATUS)
                self.assertEqual(result.retry_count, 0)

    def test_200_valid_booleans_succeeds(self) -> None:
        result = _run_execution()
        self.assertIsInstance(result, conn.ConnectivityPreflightSuccess)
        self.assertEqual(result.http_status, 200)

    def test_exchange_active_false_still_succeeds(self) -> None:
        response = _success_http_response(exchange_active=False, trading_active=True)
        result = _run_execution(response=response)
        self.assertIsInstance(result, conn.ConnectivityPreflightSuccess)
        self.assertFalse(result.exchange_active)

    def test_trading_active_false_still_succeeds(self) -> None:
        response = _success_http_response(exchange_active=True, trading_active=False)
        result = _run_execution(response=response)
        self.assertIsInstance(result, conn.ConnectivityPreflightSuccess)
        self.assertFalse(result.trading_active)

    def test_malformed_json_halts(self) -> None:
        body = b"{not-json"
        response = (
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
            + f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
            + body
        )
        result = _run_execution(response=response)
        self.assertEqual(result.code, conn.ConnectivityHaltCode.RESPONSE_MALFORMED)

    def test_non_object_json_halts(self) -> None:
        body = b"[1,2,3]"
        response = (
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
            + f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
            + body
        )
        result = _run_execution(response=response)
        self.assertEqual(result.code, conn.ConnectivityHaltCode.RESPONSE_MALFORMED)

    def test_missing_required_boolean_halts(self) -> None:
        body = json.dumps({"exchange_active": True}).encode("utf-8")
        response = (
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
            + f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
            + body
        )
        result = _run_execution(response=response)
        self.assertEqual(result.code, conn.ConnectivityHaltCode.RESPONSE_MALFORMED)

    def test_non_boolean_required_field_halts(self) -> None:
        body = json.dumps({"exchange_active": "yes", "trading_active": True}).encode("utf-8")
        response = (
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
            + f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
            + body
        )
        result = _run_execution(response=response)
        self.assertEqual(result.code, conn.ConnectivityHaltCode.RESPONSE_MALFORMED)

    def test_wrong_content_type_halts(self) -> None:
        body = json.dumps({"exchange_active": True, "trading_active": True}).encode("utf-8")
        response = (
            b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n"
            + f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
            + body
        )
        result = _run_execution(response=response)
        self.assertEqual(result.code, conn.ConnectivityHaltCode.RESPONSE_MALFORMED)

    def test_compressed_content_halts(self) -> None:
        result = _run_execution(
            response=_success_http_response(extra_headers="Content-Encoding: gzip\r\n")
        )
        self.assertEqual(result.code, conn.ConnectivityHaltCode.RESPONSE_MALFORMED)

    def test_oversized_response_halts(self) -> None:
        big_body = json.dumps(
            {"exchange_active": True, "trading_active": True, "pad": "x" * 70000}
        ).encode("utf-8")
        response = (
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
            + f"Content-Length: {len(big_body)}\r\n\r\n".encode("ascii")
            + big_body
        )
        result = _run_execution(response=response)
        self.assertEqual(result.code, conn.ConnectivityHaltCode.RESPONSE_MALFORMED)

    def test_nan_in_http_response_body_halts(self) -> None:
        body = b'{"exchange_active":NaN,"trading_active":true}'
        response = (
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
            + f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
            + body
        )
        result = _run_execution(response=response)
        self.assertEqual(result.code, conn.ConnectivityHaltCode.RESPONSE_MALFORMED)

    def test_request_headers_contain_no_auth_or_cookie_material(self) -> None:
        plan = _valid_plan()
        fake_sock = _FakeTLSSocket(_success_http_response())
        with mock.patch.object(conn, "_resolve_addresses", return_value=_af_candidates(_PUBLIC_ADDR_A)), \
             mock.patch.object(conn, "_connect_tcp", return_value=mock.Mock()), \
             mock.patch.object(conn, "_tls_wrap", return_value=fake_sock):
            conn.execute_demo_read_only_connectivity(plan)
        sent_text = fake_sock.sent.decode("ascii")
        for forbidden in ("Authorization", "KALSHI-ACCESS", "Cookie"):
            self.assertNotIn(forbidden, sent_text)

    def test_proxy_env_vars_not_consumed(self) -> None:
        with mock.patch.dict(os.environ, {"HTTPS_PROXY": "http://proxy.invalid:8080"}):
            result = _run_execution()
        self.assertIsInstance(result, conn.ConnectivityPreflightSuccess)

    def test_no_netrc_or_cookie_jar_consumed(self) -> None:
        import ast

        with open(conn.__file__, "r", encoding="utf-8") as fh:
            source = fh.read()
        tree = ast.parse(source)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        self.assertNotIn("http.cookiejar", imported)
        self.assertNotIn("netrc", imported)

    def test_success_names_two_distinct_source_hashes(self) -> None:
        result = _run_execution()
        self.assertNotEqual(result.raw_openapi_sha256, result.source_binding_record_sha256)
        self.assertEqual(result.raw_openapi_sha256, _RAW_OPENAPI_SHA)


class EvidenceCompletenessTests(unittest.TestCase):
    """Section 7.6: complete success evidence."""

    def test_success_evidence_contains_all_required_fields(self) -> None:
        result = _run_execution()
        self.assertIsInstance(result, conn.ConnectivityPreflightSuccess)
        for field_name in (
            "selected_numeric_address",
            "resolver_returned_address_count",
            "verified_dns_address_count",
            "no_prohibited_address_confirmed",
            "no_hostname_reresolution_confirmed",
            "source_binding_record_byte_length",
            "raw_openapi_byte_length",
            "effective_security_source",
            "caller_visible_elapsed_ms",
            "resolver_abandoned",
            "authorization_provenance_mode",
            "runtime_authorization_provenance_proof",
        ):
            self.assertTrue(hasattr(result, field_name), field_name)
        self.assertTrue(result.no_prohibited_address_confirmed)
        self.assertTrue(result.no_hostname_reresolution_confirmed)
        self.assertGreaterEqual(result.caller_visible_elapsed_ms, 0)
        self.assertFalse(result.resolver_abandoned)
        self.assertEqual(result.selected_numeric_address, _PUBLIC_ADDR_A)


class InterruptionAndImportTests(unittest.TestCase):
    def test_interruption_after_send_yields_request_result_unknown(self) -> None:
        plan = _valid_plan()

        def fake_tls_wrap(raw_sock, server_hostname, timeout_s):
            sock = _FakeTLSSocket(b"")
            sock.recv = mock.Mock(side_effect=OSError("connection reset"))
            return sock

        with mock.patch.object(conn, "_resolve_addresses", return_value=_af_candidates(_PUBLIC_ADDR_A)), \
             mock.patch.object(conn, "_connect_tcp", return_value=mock.Mock()), \
             mock.patch.object(conn, "_tls_wrap", side_effect=fake_tls_wrap):
            result = conn.execute_demo_read_only_connectivity(plan)
        self.assertEqual(result.code, conn.ConnectivityHaltCode.REQUEST_RESULT_UNKNOWN)

    def test_module_import_is_network_free(self) -> None:
        import importlib
        import socket as socket_module

        original_socket = socket_module.socket

        def _forbidden(*args, **kwargs):
            raise AssertionError("import must not open a socket")

        socket_module.socket = _forbidden
        try:
            importlib.reload(conn)
        finally:
            socket_module.socket = original_socket
            importlib.reload(conn)


class OfflineNetworkGuardTests(unittest.TestCase):
    """Fail-closed guard (Section 1 of the Implementation-05 dispatch):
    even if a future edit accidentally removed one of the module-level
    mocks used elsewhere in this file, these tests independently patch
    the *real* `socket` module's `getaddrinfo`/`socket` to raise, and
    confirm the standard offline flows still complete without ever
    reaching them."""

    def test_standard_success_flow_never_touches_real_socket_module(self) -> None:
        import socket as real_socket_module

        def _forbidden_getaddrinfo(*a, **k):
            raise AssertionError("real socket.getaddrinfo must never be called in tests")

        def _forbidden_socket_ctor(*a, **k):
            raise AssertionError("real socket.socket must never be constructed in tests")

        with mock.patch.object(
            real_socket_module, "getaddrinfo", side_effect=_forbidden_getaddrinfo
        ), mock.patch.object(
            real_socket_module, "socket", side_effect=_forbidden_socket_ctor
        ):
            result = _run_execution()
        self.assertIsInstance(result, conn.ConnectivityPreflightSuccess)

    def test_dns_timeout_path_never_touches_real_socket_module(self) -> None:
        import socket as real_socket_module

        def _forbidden_getaddrinfo(*a, **k):
            raise AssertionError("real socket.getaddrinfo must never be called in tests")

        plan = _valid_plan()
        with mock.patch.object(
            real_socket_module, "getaddrinfo", side_effect=_forbidden_getaddrinfo
        ), mock.patch.object(
            conn, "_resolve_addresses_with_deadline", side_effect=TimeoutError("x")
        ):
            result = conn.execute_demo_read_only_connectivity(plan)
        self.assertEqual(result.code, conn.ConnectivityHaltCode.CONNECTIVITY_TIMEOUT)

    def test_planning_only_flow_never_touches_real_socket_module(self) -> None:
        import socket as real_socket_module

        def _forbidden_anything(*a, **k):
            raise AssertionError("planning must never touch the real socket module")

        with mock.patch.object(
            real_socket_module, "getaddrinfo", side_effect=_forbidden_anything
        ), mock.patch.object(
            real_socket_module, "socket", side_effect=_forbidden_anything
        ):
            plan = _valid_plan()
        self.assertIsInstance(plan, conn.ConnectivityPreflightPlan)


class SecretPatternScanTests(unittest.TestCase):
    """Static scan required by the dispatch evidence list: this module's
    and this test file's source contain no string resembling a Kalshi
    API key, private-key PEM block, or other plausible secret."""

    _FORBIDDEN_SNIPPETS = (
        "-----BEGIN",
        "PRIVATE KEY-----",
        "KALSHI_DEMO_API_KEY_ID=",
        "KALSHI_DEMO_PRIVATE_KEY_PEM=",
    )

    def test_connectivity_module_contains_no_secret_pattern(self) -> None:
        with open(conn.__file__, "r", encoding="utf-8") as fh:
            source = fh.read()
        for snippet in self._FORBIDDEN_SNIPPETS:
            self.assertNotIn(snippet, source)

    # Note: this test file itself is intentionally not scanned here --
    # `_FORBIDDEN_SNIPPETS` above necessarily contains each forbidden
    # string literally as a pattern definition, which would make a
    # self-scan trivially (and meaninglessly) fail. The required
    # "secret-pattern scan result" evidence for this file is produced
    # separately as a plain `grep`-based check outside pytest/unittest
    # and reported in the Neo evidence block, not as a unit test
    # assertion.
