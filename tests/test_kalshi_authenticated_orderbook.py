"""Offline unit tests for Kalshi Demo authenticated REST order-book
reconstruction, Implementation 06
(`KALSHI_DEMO_ONE_MARKET_AUTHENTICATED_REST_ORDER_BOOK_RECONSTRUCTION_SPEC_01.md`
Section 16), a same-scope correction of Marco-blocked Implementation 05.

This file's own identity is Implementation 06. Prior implementations
(03, 04, 05) are referenced below only as historical changelog context
for what each correction round fixed; none of those references claims
this file's current task identity.

All DNS, socket, TLS, and HTTP behavior in this file is fake/mocked. No
test in this file contacts Kalshi, Polymarket, or any other external
endpoint. Generated in-memory RSA test keys are used for signing tests;
none resembles or is ever mistaken for a real credential. The exact
accepted 1556-byte Section 9.2 record is used verbatim as the base test
fixture -- it is never fabricated or structurally altered except in
tests that specifically prove tampering is rejected.
"""

from __future__ import annotations

import decimal
import hashlib
import ipaddress
import json
import os
import socket
import ssl
import unittest
from dataclasses import replace
from unittest import mock

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from arb.venues.kalshi import (
    AuthorizationValue as AV,
    CredentialReferenceKind as CRK,
    CredentialReferenceState as CRS,
    EndpointComponents,
    Environment,
    RequestedCapability as RC,
    TaskAuthorizationCapabilityEnvelope as Envelope,
    ValidatedDemoProfile,
)
import arb.venues.kalshi.orderbook as ob

_ACCEPTED_API_KEY_NAME = "KALSHI_DEMO_API_KEY_ID"
_ACCEPTED_PEM_NAME = "KALSHI_DEMO_PRIVATE_KEY_PEM"
_PUBLIC_ADDR_A = "1.2.3.4"
_PUBLIC_ADDR_B = "1.2.3.5"
_PRIVATE_ADDR = "10.0.0.5"

# Exact accepted Section 9.2 record, taken verbatim from the controlling
# specification. 1556 bytes, SHA-256
# 295224b34fcd6adde7f54605388286e515b961eb512f631269fc2cbdd0544d0d.
_ACCEPTED_RECORD_BYTES = (
    b'{"binding_schema_revision":1,"effective_auth_classification":'
    b'"AUTHENTICATED_READ_ONLY","effective_security":[{"kalshiAccessKey":[],'
    b'"kalshiAccessSignature":[],"kalshiAccessTimestamp":[]}],'
    b'"effective_security_source":"OPERATION_OVERRIDE","http_status":200,'
    b'"normalized_source_media_type":"text/yaml","openapi_version":"3.0.0",'
    b'"operation_method":"GET","operation_path_template":'
    b'"/markets/{ticker}/orderbook","operation_security_key_present":true,'
    b'"planned_query_policy":"OMIT_DEPTH_AND_QUERY_STRING","query_parameters":'
    b'{"depth":{"default":0,"maximum":100,"minimum":0,"required":false,'
    b'"type":"integer"}},"raw_openapi_byte_length":323631,"raw_openapi_sha256":'
    b'"6e6402bf667da7596b5074ba1c687cdcb6e67f73903f49fd6b94f4b83a6a22de",'
    b'"required_auth_header_names":["KALSHI-ACCESS-KEY","KALSHI-ACCESS-SIGNATURE",'
    b'"KALSHI-ACCESS-TIMESTAMP"],"response_200":{"level_shape":'
    b'["price_dollars_string","count_fp_string"],"media_type":"application/json",'
    b'"orderbook_fp_required_fields":["no_dollars","yes_dollars"],'
    b'"required_top_level_fields":["orderbook_fp"]},"retrieved_at_utc":'
    b'"2026-08-08T12:41:45Z","reviewed_demo_rest_origin":'
    b'"https://external-api.demo.kalshi.co","reviewed_full_request_path_template":'
    b'"/trade-api/v2/markets/{ticker}/orderbook","schema_version":1,'
    b'"security_scheme_names":["kalshiAccessKey","kalshiAccessSignature",'
    b'"kalshiAccessTimestamp"],"source_info_version":"3.27.0","source_url":'
    b'"https://docs.kalshi.com/openapi.yaml","ticker_parameter":{"in":"path",'
    b'"maximum_length":null,"minimum_length":null,"name":"ticker","pattern":null,'
    b'"required":true,"type":"string"}}'
)

_ACCEPTED_RECORD_SHA256 = "295224b34fcd6adde7f54605388286e515b961eb512f631269fc2cbdd0544d0d"
_ACCEPTED_RAW_OPENAPI_SHA256 = "6e6402bf667da7596b5074ba1c687cdcb6e67f73903f49fd6b94f4b83a6a22de"
_ACCEPTED_SPEC_SHA256 = "ae8a57069a261c35c5a204d3358091c7ae3f0f9ddbe1cdbe6c8fb20f9250ead8"


class VerifyFixtureIdentityTests(unittest.TestCase):
    """Proves the test fixture itself is the exact accepted record before
    any other test relies on it."""

    def test_fixture_byte_length_is_exactly_1556(self):
        self.assertEqual(len(_ACCEPTED_RECORD_BYTES), 1556)

    def test_fixture_sha256_matches_accepted_identity(self):
        self.assertEqual(hashlib.sha256(_ACCEPTED_RECORD_BYTES).hexdigest(), _ACCEPTED_RECORD_SHA256)

    def test_fixture_matches_module_constant(self):
        self.assertEqual(
            hashlib.sha256(_ACCEPTED_RECORD_BYTES).hexdigest(),
            ob._ACCEPTED_SOURCE_BINDING_RECORD_SHA256,
        )


# ---------------------------------------------------------------------------
# Shared fixtures.
# ---------------------------------------------------------------------------


def _envelope(**overrides: AV) -> Envelope:
    fields = dict(
        schema_version=1,
        authorization_id="AUTH-OB-06",
        authorizing_authority="Gustavo",
        task_id="KALSHI_DEMO_ONE_MARKET_AUTHENTICATED_REST_ORDER_BOOK_RECONSTRUCTION_IMPLEMENTATION_06",
        issue_date="2026-08-08",
        completion_rule="single-request",
        network_access=AV.PERMITTED,
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
        repository_commits=AV.PROHIBITED,
    )
    fields.update(overrides)
    return Envelope(**fields)


def _profile(credential_reference_states=None, **overrides) -> ValidatedDemoProfile:
    if credential_reference_states is None:
        credential_reference_states = (
            (CRK.API_KEY_ID_ENV_SOURCE, CRS.CONFIGURED),
            (CRK.PRIVATE_KEY_PEM_ENV_SOURCE, CRS.CONFIGURED),
        )
    fields = dict(
        environment=Environment.KALSHI_DEMO,
        rest=EndpointComponents(
            scheme="https", host="external-api.demo.kalshi.co", port=443,
            path="/trade-api/v2", has_user_info=False, has_query=False, has_fragment=False,
        ),
        websocket=EndpointComponents(
            scheme="wss", host="external-api-ws.demo.kalshi.co", port=443,
            path="/trade-api/ws/v2", has_user_info=False, has_query=False, has_fragment=False,
        ),
        requested_capability=RC.DEMO_AUTHENTICATED_READ,
        effective_capability=RC.DEMO_AUTHENTICATED_READ,
        credential_reference_states=credential_reference_states,
        allowlist_revision="candidate-02",
        validation_schema_revision=1,
    )
    fields.update(overrides)
    return ValidatedDemoProfile(**fields)


def _expectation(**overrides) -> ob.OrderBookExecutionDispatchExpectation:
    fields = dict(
        gustavo_execution_authorization_id="AUTH-OB-03",
        expected_raw_openapi_sha256=_ACCEPTED_RAW_OPENAPI_SHA256,
        expected_source_binding_record_sha256=_ACCEPTED_RECORD_SHA256,
        expected_specification_sha256=_ACCEPTED_SPEC_SHA256,
        expected_implementation_commit="a" * 40,
    )
    fields.update(overrides)
    return ob.OrderBookExecutionDispatchExpectation(**fields)


def _valid_input(ticker="BTC_USD", profile=None, envelope=None, expectation=None, record_bytes=None):
    return ob.AuthenticatedOrderBookInput(
        validated_demo_profile=profile or _profile(),
        authorization_envelope=envelope or _envelope(),
        operation_capability=ob.OrderBookRestCapability.KALSHI_DEMO_AUTHENTICATED_REST_READ,
        market_ticker=ticker,
        source_binding_record_bytes=record_bytes or _ACCEPTED_RECORD_BYTES,
        execution_dispatch_expectation=expectation or _expectation(),
    )


def _valid_plan(**kwargs):
    plan = ob.plan_demo_authenticated_orderbook(_valid_input(**kwargs))
    assert isinstance(plan, ob.AuthenticatedOrderBookPlan), plan
    return plan


_RSA_KEY_CACHE = {}


def _test_rsa_key_pem() -> bytes:
    if "key" not in _RSA_KEY_CACHE:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        _RSA_KEY_CACHE["key"] = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        _RSA_KEY_CACHE["public"] = key.public_key()
    return _RSA_KEY_CACHE["key"]


def _test_rsa_public_key():
    _test_rsa_key_pem()
    return _RSA_KEY_CACHE["public"]


def _af_candidate(address_text, port=443):
    parsed = ipaddress.ip_address(address_text)
    if parsed.version == 4:
        return (socket.AF_INET, (address_text, port))
    return (socket.AF_INET6, (address_text, port, 0, 0))


def _http_response(status=200, body=b"", content_type="application/json", extra_headers=""):
    header = (
        f"HTTP/1.1 {status} X\r\n"
        f"Content-Type: {content_type}\r\n"
        "Content-Encoding: identity\r\n"
        f"{extra_headers}"
        "\r\n"
    ).encode("ascii")
    return header + body


def _valid_orderbook_body():
    return json.dumps(
        {
            "orderbook_fp": {
                "yes_dollars": [["0.5000", "100"], ["0.6000", "50.25"]],
                "no_dollars": [["0.4000", "75"]],
            }
        }
    ).encode("utf-8")


class _FakeSSLSocket:
    """Buffer-based fake TLS socket. Honors the exact `recv(n)` argument
    (returns at most `n` bytes, exactly like a real socket may) and
    records every requested/returned byte count so tests can prove the
    executor's bounded-body-reception behavior (Implementation-05
    correction 3)."""

    def __init__(self, chunks=(), raise_on_send=None, raise_on_recv=None):
        self._buffer = b"".join(chunks)
        self.sent = []
        self._raise_on_send = raise_on_send
        self._raise_on_recv = raise_on_recv
        self.recv_requested_sizes = []
        self.recv_returned_sizes = []

    def settimeout(self, _t):
        pass

    def sendall(self, data):
        if self._raise_on_send:
            raise self._raise_on_send
        self.sent.append(data)

    def recv(self, n):
        self.recv_requested_sizes.append(n)
        if not self._buffer and self._raise_on_recv:
            raise self._raise_on_recv
        chunk = self._buffer[:n]
        self._buffer = self._buffer[n:]
        self.recv_returned_sizes.append(len(chunk))
        return chunk

    def close(self):
        pass


class _MonkeyPatch:
    def __init__(self):
        self._restores = []

    def setattr(self, obj, name, value):
        self._restores.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    def undo(self):
        for obj, name, value in reversed(self._restores):
            setattr(obj, name, value)


def _patch_network(monkey, *, chunks=(), raise_on_send=None, raise_on_recv=None):
    fake_tls = _FakeSSLSocket(chunks=chunks, raise_on_send=raise_on_send, raise_on_recv=raise_on_recv)

    def fake_getaddrinfo(host, port, family, socktype):
        return [(socket.AF_INET, socktype, 0, "", (_PUBLIC_ADDR_A, port))]

    class FakeRawSocket:
        def __init__(self, *_a, **_kw):
            pass

        def settimeout(self, _t):
            pass

        def connect(self, _addr):
            pass

        def close(self):
            pass

    class FakeContext:
        minimum_version = None
        check_hostname = None
        verify_mode = None

        def wrap_socket(self, _sock, server_hostname=None):
            return fake_tls

    monkey.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    monkey.setattr(socket, "socket", FakeRawSocket)
    monkey.setattr(ssl, "create_default_context", lambda: FakeContext())
    return fake_tls


# ---------------------------------------------------------------------------
# 16.1 Capability/environment.
# ---------------------------------------------------------------------------


class CapabilityEnvironmentTests(unittest.TestCase):
    def test_exact_capability_accepted(self):
        plan = ob.plan_demo_authenticated_orderbook(_valid_input())
        self.assertIsInstance(plan, ob.AuthenticatedOrderBookPlan)
        self.assertIs(
            plan.operation_capability, ob.OrderBookRestCapability.KALSHI_DEMO_AUTHENTICATED_REST_READ
        )

    def test_public_read_capability_substitution_rejected(self):
        profile = _profile(requested_capability=RC.DEMO_PUBLIC_REST_READ, effective_capability=RC.DEMO_PUBLIC_REST_READ)
        result = ob.plan_demo_authenticated_orderbook(_valid_input(profile=profile))
        self.assertIsInstance(result, ob.OrderBookHalt)
        self.assertEqual(result.code, ob.OrderBookHaltCode.REST_AUTHENTICATED_READ_REQUIRED)

    def test_demo_write_rejected(self):
        envelope = _envelope(demo_writes=AV.PERMITTED)
        result = ob.plan_demo_authenticated_orderbook(_valid_input(envelope=envelope))
        self.assertIsInstance(result, ob.OrderBookHalt)
        self.assertEqual(result.code, ob.OrderBookHaltCode.PRODUCTION_ACCESS_PROHIBITED)

    def test_production_read_rejected(self):
        envelope = _envelope(production_authenticated_reads=AV.PERMITTED)
        result = ob.plan_demo_authenticated_orderbook(_valid_input(envelope=envelope))
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_production_write_rejected(self):
        envelope = _envelope(production_writes=AV.PERMITTED)
        result = ob.plan_demo_authenticated_orderbook(_valid_input(envelope=envelope))
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_unknown_capability_type_rejected(self):
        input_data = _valid_input()
        object.__setattr__(input_data, "operation_capability", "KALSHI_DEMO_AUTHENTICATED_REST_READ")
        result = ob.plan_demo_authenticated_orderbook(input_data)
        self.assertIsInstance(result, ob.OrderBookHalt)
        self.assertEqual(result.code, ob.OrderBookHaltCode.REST_AUTHENTICATED_READ_REQUIRED)

    def test_endpoint_environment_mismatch_rejected(self):
        profile = _profile(
            rest=EndpointComponents(
                scheme="https", host="external-api.kalshi.com", port=443,
                path="/trade-api/v2", has_user_info=False, has_query=False, has_fragment=False,
            )
        )
        result = ob.plan_demo_authenticated_orderbook(_valid_input(profile=profile))
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_non_input_type_rejected(self):
        result = ob.plan_demo_authenticated_orderbook("not an input")
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_websocket_capability_cannot_reach_executor(self):
        # There is no capability value representing WebSocket in
        # OrderBookRestCapability -- the closed enum structurally
        # excludes it.
        members = list(ob.OrderBookRestCapability)
        self.assertEqual(len(members), 1)
        self.assertEqual(members[0].value, "KALSHI_DEMO_AUTHENTICATED_REST_READ")


# ---------------------------------------------------------------------------
# 16.2 Credential references.
# ---------------------------------------------------------------------------


class CredentialReferenceTests(unittest.TestCase):
    def test_missing_api_key_reference_rejected(self):
        profile = _profile(credential_reference_states=((CRK.PRIVATE_KEY_PEM_ENV_SOURCE, CRS.CONFIGURED),))
        result = ob.plan_demo_authenticated_orderbook(_valid_input(profile=profile))
        self.assertIsInstance(result, ob.OrderBookHalt)
        self.assertEqual(result.code, ob.OrderBookHaltCode.CREDENTIAL_REFERENCE_MISSING)

    def test_missing_private_key_reference_rejected(self):
        profile = _profile(credential_reference_states=((CRK.API_KEY_ID_ENV_SOURCE, CRS.CONFIGURED),))
        result = ob.plan_demo_authenticated_orderbook(_valid_input(profile=profile))
        self.assertIsInstance(result, ob.OrderBookHalt)
        self.assertEqual(result.code, ob.OrderBookHaltCode.CREDENTIAL_REFERENCE_MISSING)

    def test_placeholder_each_rejected(self):
        profile = _profile(
            credential_reference_states=(
                (CRK.API_KEY_ID_ENV_SOURCE, CRS.PLACEHOLDER),
                (CRK.PRIVATE_KEY_PEM_ENV_SOURCE, CRS.CONFIGURED),
            )
        )
        result = ob.plan_demo_authenticated_orderbook(_valid_input(profile=profile))
        self.assertEqual(result.code, ob.OrderBookHaltCode.CREDENTIAL_PLACEHOLDER)

    def test_placeholder_both_rejected(self):
        profile = _profile(
            credential_reference_states=(
                (CRK.API_KEY_ID_ENV_SOURCE, CRS.PLACEHOLDER),
                (CRK.PRIVATE_KEY_PEM_ENV_SOURCE, CRS.PLACEHOLDER),
            )
        )
        result = ob.plan_demo_authenticated_orderbook(_valid_input(profile=profile))
        self.assertEqual(result.code, ob.OrderBookHaltCode.CREDENTIAL_PLACEHOLDER)

    def test_not_required_each_rejected(self):
        profile = _profile(
            credential_reference_states=(
                (CRK.API_KEY_ID_ENV_SOURCE, CRS.NOT_REQUIRED),
                (CRK.PRIVATE_KEY_PEM_ENV_SOURCE, CRS.CONFIGURED),
            )
        )
        result = ob.plan_demo_authenticated_orderbook(_valid_input(profile=profile))
        self.assertEqual(result.code, ob.OrderBookHaltCode.CREDENTIAL_NOT_REQUIRED_INVALID)

    def test_not_required_both_rejected(self):
        profile = _profile(
            credential_reference_states=(
                (CRK.API_KEY_ID_ENV_SOURCE, CRS.NOT_REQUIRED),
                (CRK.PRIVATE_KEY_PEM_ENV_SOURCE, CRS.NOT_REQUIRED),
            )
        )
        result = ob.plan_demo_authenticated_orderbook(_valid_input(profile=profile))
        self.assertEqual(result.code, ob.OrderBookHaltCode.CREDENTIAL_NOT_REQUIRED_INVALID)

    def test_both_configured_accepted(self):
        plan = ob.plan_demo_authenticated_orderbook(_valid_input())
        self.assertIsInstance(plan, ob.AuthenticatedOrderBookPlan)

    def test_duplicate_kind_entries_rejected(self):
        # Implementation-05 correction 6: a duplicate kind entry must be
        # rejected structurally, never silently collapsed through a
        # dict before validation.
        profile = _profile(
            credential_reference_states=(
                (CRK.API_KEY_ID_ENV_SOURCE, CRS.CONFIGURED),
                (CRK.API_KEY_ID_ENV_SOURCE, CRS.CONFIGURED),
            )
        )
        result = ob.plan_demo_authenticated_orderbook(_valid_input(profile=profile))
        self.assertIsInstance(result, ob.OrderBookHalt)
        self.assertEqual(result.code, ob.OrderBookHaltCode.CREDENTIAL_REFERENCE_MALFORMED)

    def test_duplicate_kind_with_differing_states_rejected(self):
        # Even if the two duplicate-kind entries have different states
        # (e.g. one CONFIGURED, one PLACEHOLDER), the duplicate itself
        # is the defect -- a dict-collapse would silently keep only one
        # and might let this through.
        profile = _profile(
            credential_reference_states=(
                (CRK.API_KEY_ID_ENV_SOURCE, CRS.CONFIGURED),
                (CRK.API_KEY_ID_ENV_SOURCE, CRS.PLACEHOLDER),
                (CRK.PRIVATE_KEY_PEM_ENV_SOURCE, CRS.CONFIGURED),
            )
        )
        result = ob.plan_demo_authenticated_orderbook(_valid_input(profile=profile))
        self.assertIsInstance(result, ob.OrderBookHalt)
        self.assertEqual(result.code, ob.OrderBookHaltCode.CREDENTIAL_REFERENCE_MALFORMED)

    def test_extra_unexpected_kind_entry_rejected(self):
        profile = _profile(
            credential_reference_states=(
                (CRK.API_KEY_ID_ENV_SOURCE, CRS.CONFIGURED),
                (CRK.PRIVATE_KEY_PEM_ENV_SOURCE, CRS.CONFIGURED),
                (CRK.API_KEY_ID_ENV_SOURCE, CRS.CONFIGURED),
            )
        )
        # This is simultaneously "extra" and "duplicate" -- either
        # classification is an acceptable rejection reason, but it must
        # be rejected.
        result = ob.plan_demo_authenticated_orderbook(_valid_input(profile=profile))
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_empty_collection_rejected_as_missing(self):
        profile = _profile(credential_reference_states=())
        result = ob.plan_demo_authenticated_orderbook(_valid_input(profile=profile))
        self.assertIsInstance(result, ob.OrderBookHalt)
        self.assertEqual(result.code, ob.OrderBookHaltCode.CREDENTIAL_REFERENCE_MISSING)

    def test_malformed_entry_shape_rejected(self):
        profile = _profile(
            credential_reference_states=(
                (CRK.API_KEY_ID_ENV_SOURCE,),  # 1-tuple, not a (kind, state) pair
                (CRK.PRIVATE_KEY_PEM_ENV_SOURCE, CRS.CONFIGURED),
            )
        )
        result = ob.plan_demo_authenticated_orderbook(_valid_input(profile=profile))
        self.assertIsInstance(result, ob.OrderBookHalt)
        self.assertEqual(result.code, ob.OrderBookHaltCode.CREDENTIAL_REFERENCE_MALFORMED)

    def test_malformed_entry_not_a_tuple_rejected(self):
        profile = _profile(
            credential_reference_states=(
                ["not", "a", "tuple"],
                (CRK.PRIVATE_KEY_PEM_ENV_SOURCE, CRS.CONFIGURED),
            )
        )
        result = ob.plan_demo_authenticated_orderbook(_valid_input(profile=profile))
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_malformed_kind_type_rejected(self):
        profile = _profile(
            credential_reference_states=(
                ("API_KEY_ID_ENV_SOURCE", CRS.CONFIGURED),  # plain str, not the enum
                (CRK.PRIVATE_KEY_PEM_ENV_SOURCE, CRS.CONFIGURED),
            )
        )
        result = ob.plan_demo_authenticated_orderbook(_valid_input(profile=profile))
        self.assertIsInstance(result, ob.OrderBookHalt)
        self.assertEqual(result.code, ob.OrderBookHaltCode.CREDENTIAL_REFERENCE_MALFORMED)

    def test_hardcoded_env_var_names(self):
        self.assertEqual(ob._API_KEY_ID_ENV_VAR, "KALSHI_DEMO_API_KEY_ID")
        self.assertEqual(ob._PRIVATE_KEY_PEM_ENV_VAR, "KALSHI_DEMO_PRIVATE_KEY_PEM")

    def test_secret_absent_from_ephemeral_secrets_repr(self):
        secrets = ob._EphemeralOrderBookSecrets(api_key_id="not-a-real-key", private_key_pem=b"not-a-real-pem")
        text = repr(secrets)
        self.assertNotIn("not-a-real-key", text)
        self.assertNotIn("not-a-real-pem", text)
        self.assertIn("REDACTED", text)

    def test_loader_reads_exactly_two_env_vars_no_fallback(self):
        os.environ["TEST_API_KEY_ID_LOAD"] = "x"
        try:
            plan = _valid_plan()
            os.environ.pop(_ACCEPTED_API_KEY_NAME, None)
            os.environ.pop(_ACCEPTED_PEM_NAME, None)
            with self.assertRaises(ob._HaltingError) as ctx:
                ob._load_demo_orderbook_secrets(plan)
            self.assertEqual(ctx.exception.code, ob.OrderBookHaltCode.CREDENTIAL_REFERENCE_MISSING)
        finally:
            os.environ.pop("TEST_API_KEY_ID_LOAD", None)


class ApiKeyIdSafetyTests(unittest.TestCase):
    """Implementation-04 correction 4: the loaded API-key identifier
    remains opaque and byte-for-byte unchanged, but is proven compatible
    with the exact ASCII HTTP header serialization before use."""

    def test_valid_ascii_key_accepted(self):
        self.assertTrue(ob._api_key_id_is_header_safe("valid-key-ABC123_.~"))

    def test_empty_value_rejected(self):
        self.assertFalse(ob._api_key_id_is_header_safe(""))

    def test_cr_rejected(self):
        self.assertFalse(ob._api_key_id_is_header_safe("a\rb"))

    def test_lf_rejected(self):
        self.assertFalse(ob._api_key_id_is_header_safe("a\nb"))

    def test_crlf_rejected(self):
        self.assertFalse(ob._api_key_id_is_header_safe("a\r\nInjected-Header: x"))

    def test_other_http_controls_rejected(self):
        for cp in (0x00, 0x01, 0x08, 0x1b, 0x1f):
            self.assertFalse(ob._api_key_id_is_header_safe(f"a{chr(cp)}b"), hex(cp))

    def test_del_rejected(self):
        self.assertFalse(ob._api_key_id_is_header_safe("a\x7fb"))

    def test_non_ascii_unicode_rejected(self):
        for bad in ("kéy", "ключ", "键", "a\u200bb", "café", "𝐤𝐞𝐲"):
            self.assertFalse(ob._api_key_id_is_header_safe(bad), bad)

    def test_non_ascii_value_never_raises_unicode_encode_error(self):
        # The check itself must never raise -- it always returns False
        # for anything it cannot represent in the exact ASCII
        # serialization this implementation uses.
        for bad in ("kéy", "ключ", "🔑", "\ud800"):
            try:
                result = ob._api_key_id_is_header_safe(bad)
            except UnicodeEncodeError:
                self.fail(f"UnicodeEncodeError escaped for {bad!r}")
            self.assertFalse(result)

    def test_value_never_stripped_or_cased(self):
        # The safety check does not mutate; a value with meaningful
        # leading/trailing content or mixed case must round-trip exactly
        # once accepted.
        value = " MixedCase-Key_123 "
        # Leading/trailing space is itself a printable ASCII character
        # here (not a control character), so it is accepted as-is --
        # the check never trims it.
        self.assertTrue(ob._api_key_id_is_header_safe(value))
        self.assertEqual(value, " MixedCase-Key_123 ")

    def test_wrong_type_rejected(self):
        self.assertFalse(ob._api_key_id_is_header_safe(12345))
        self.assertFalse(ob._api_key_id_is_header_safe(b"bytes-not-str"))
        self.assertFalse(ob._api_key_id_is_header_safe(None))


# ---------------------------------------------------------------------------
# 16.3 Signing-message construction.
# ---------------------------------------------------------------------------


class SigningMessageTests(unittest.TestCase):
    def test_exact_timestamp_method_path_bytes(self):
        plan = _valid_plan()
        msg = ob.build_orderbook_signing_message(plan, "1700000000000")
        self.assertEqual(
            msg.message_bytes, b"1700000000000GET/trade-api/v2/markets/BTC_USD/orderbook"
        )

    def test_trade_api_v2_included(self):
        plan = _valid_plan()
        msg = ob.build_orderbook_signing_message(plan, "1")
        self.assertIn(b"/trade-api/v2", msg.message_bytes)

    def test_host_excluded_from_signing_bytes(self):
        plan = _valid_plan()
        msg = ob.build_orderbook_signing_message(plan, "1")
        self.assertNotIn(b"external-api.demo.kalshi.co", msg.message_bytes)

    def test_query_excluded_and_absent(self):
        plan = _valid_plan()
        self.assertEqual(plan.query_policy, "OMIT_DEPTH_AND_QUERY_STRING")
        msg = ob.build_orderbook_signing_message(plan, "1")
        self.assertNotIn(b"?", msg.message_bytes)
        self.assertNotIn(b"depth", msg.message_bytes)

    def test_malformed_timestamp_rejected(self):
        plan = _valid_plan()
        for bad in ("-1", "1.5", " 1", "1 ", "+1", "01", "abc", ""):
            with self.assertRaises(ob._HaltingError, msg=bad):
                ob.build_orderbook_signing_message(plan, bad)

    def test_deterministic_repeated_construction(self):
        plan = _valid_plan()
        msg1 = ob.build_orderbook_signing_message(plan, "1700000000000")
        msg2 = ob.build_orderbook_signing_message(plan, "1700000000000")
        self.assertEqual(msg1.message_bytes, msg2.message_bytes)

    def test_wrong_method_rejected_by_signer_binding_check(self):
        plan = _valid_plan()
        msg = ob.build_orderbook_signing_message(plan, "1")
        tampered = replace(msg, method="POST")
        with self.assertRaises(ob._HaltingError):
            ob._require_signing_message_bound_to_plan(tampered, plan)

    def test_wrong_route_rejected(self):
        plan = _valid_plan()
        msg = ob.build_orderbook_signing_message(plan, "1")
        tampered = replace(msg, route_template="/exchange/status")
        with self.assertRaises(ob._HaltingError):
            ob._require_signing_message_bound_to_plan(tampered, plan)

    def test_ticker_mismatch_rejected(self):
        plan = _valid_plan()
        msg = ob.build_orderbook_signing_message(plan, "1")
        tampered = replace(msg, ticker="ETH_USD")
        with self.assertRaises(ob._HaltingError):
            ob._require_signing_message_bound_to_plan(tampered, plan)

    def test_source_binding_mismatch_rejected(self):
        plan = _valid_plan()
        msg = ob.build_orderbook_signing_message(plan, "1")
        tampered = replace(msg, source_binding_record_sha256="f" * 64)
        with self.assertRaises(ob._HaltingError):
            ob._require_signing_message_bound_to_plan(tampered, plan)

    def test_signing_profile_mismatch_rejected(self):
        plan = _valid_plan()
        msg = ob.build_orderbook_signing_message(plan, "1")
        tampered = replace(msg, signing_profile="SOMETHING_ELSE")
        with self.assertRaises(ob._HaltingError) as ctx:
            ob._require_signing_message_bound_to_plan(tampered, plan)
        self.assertEqual(ctx.exception.code, ob.OrderBookHaltCode.SIGNING_PROFILE_MISMATCH)


class SigningMessageBuilderCurrentValueTests(unittest.TestCase):
    """Implementation-04 correction 8: `build_orderbook_signing_message`
    itself -- the public builder, not just the private signer -- must
    reject a plan whose accepted contract has been mutated away, before
    constructing any message bytes."""

    def test_valid_plan_succeeds(self):
        plan = _valid_plan()
        msg = ob.build_orderbook_signing_message(plan, "1700000000000")
        self.assertIsInstance(msg, ob.OrderBookSigningMessage)

    def test_wrong_method_rejected_by_public_builder(self):
        plan = _valid_plan()
        mutated = replace(plan, method="POST")
        with self.assertRaises(ob._HaltingError):
            ob.build_orderbook_signing_message(mutated, "1")

    def test_wrong_route_template_rejected_by_public_builder(self):
        plan = _valid_plan()
        mutated = replace(plan, route_template="/exchange/status")
        with self.assertRaises(ob._HaltingError):
            ob.build_orderbook_signing_message(mutated, "1")

    def test_wrong_base_path_prefix_rejected_by_public_builder(self):
        plan = _valid_plan()
        mutated = replace(plan, base_path="/other-api/v1")
        with self.assertRaises(ob._HaltingError):
            ob.build_orderbook_signing_message(mutated, "1")

    def test_ticker_path_relation_mismatch_rejected_by_public_builder(self):
        plan = _valid_plan()
        # full_path no longer matches market_ticker.
        mutated = replace(plan, full_path="/trade-api/v2/markets/SOMETHING_ELSE/orderbook")
        with self.assertRaises(ob._HaltingError):
            ob.build_orderbook_signing_message(mutated, "1")

    def test_wrong_operation_capability_rejected_by_public_builder(self):
        plan = _valid_plan()
        object.__setattr__(plan, "operation_capability", "not-an-enum")
        with self.assertRaises(ob.OrderBookTypeError):
            ob.build_orderbook_signing_message(plan, "1")

    def test_wrong_source_binding_rejected_by_public_builder(self):
        plan = _valid_plan()
        mutated = replace(plan, source_binding_record_bytes=b"garbage-not-the-accepted-record")
        with self.assertRaises(ob._HaltingError):
            ob.build_orderbook_signing_message(mutated, "1")

    def test_wrong_query_policy_rejected_by_public_builder(self):
        plan = _valid_plan()
        mutated = replace(plan, query_policy="INCLUDE_DEPTH")
        with self.assertRaises(ob._HaltingError):
            ob.build_orderbook_signing_message(mutated, "1")

    def test_wrong_signing_profile_rejected_by_public_builder(self):
        plan = _valid_plan()
        mutated = replace(plan, signing_profile="SOME_OTHER_PROFILE")
        with self.assertRaises(ob._HaltingError) as ctx:
            ob.build_orderbook_signing_message(mutated, "1")
        self.assertEqual(ctx.exception.code, ob.OrderBookHaltCode.SIGNING_PROFILE_MISMATCH)

    def test_wrong_plan_type_rejected(self):
        with self.assertRaises(ob.OrderBookTypeError):
            ob.build_orderbook_signing_message("not a plan", "1")

    def test_public_builder_never_raises_raw_exception_for_mutation(self):
        mutations = [
            ("method", "DELETE"),
            ("route_template", "/other"),
            ("base_path", "/x"),
            ("full_path", "/trade-api/v2/markets/OTHER/orderbook"),
            ("query_policy", "BAD"),
            ("signing_profile", "BAD"),
            ("source_binding_record_bytes", b"garbage"),
        ]
        for field_name, bad_value in mutations:
            with self.subTest(field=field_name):
                plan = _valid_plan()
                object.__setattr__(plan, field_name, bad_value)
                try:
                    ob.build_orderbook_signing_message(plan, "1")
                except ob._HaltingError:
                    pass  # expected -- always a typed halting error
                except Exception as exc:  # pragma: no cover - failure path
                    self.fail(f"raw exception escaped for {field_name}: {exc!r}")
                else:
                    self.fail(f"expected rejection for mutated {field_name}")


# ---------------------------------------------------------------------------
# 16.4 Cryptographic signer boundary.
# ---------------------------------------------------------------------------


class SignerBoundaryTests(unittest.TestCase):
    def test_generated_key_signs_and_verifies(self):
        plan = _valid_plan()
        msg = ob.build_orderbook_signing_message(plan, "1700000000000")
        secrets = ob._EphemeralOrderBookSecrets(api_key_id="k", private_key_pem=_test_rsa_key_pem())
        signature = ob._sign_orderbook_message(msg, plan, secrets)
        _test_rsa_public_key().verify(
            signature, msg.message_bytes,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32), hashes.SHA256(),
        )

    def test_signature_is_standard_base64(self):
        import base64
        plan = _valid_plan()
        msg = ob.build_orderbook_signing_message(plan, "1700000000000")
        secrets = ob._EphemeralOrderBookSecrets(api_key_id="k", private_key_pem=_test_rsa_key_pem())
        signature = ob._sign_orderbook_message(msg, plan, secrets)
        encoded = base64.b64encode(signature).decode("ascii")
        self.assertEqual(base64.b64decode(encoded), signature)

    def test_malformed_pem_fails(self):
        plan = _valid_plan()
        msg = ob.build_orderbook_signing_message(plan, "1")
        secrets = ob._EphemeralOrderBookSecrets(api_key_id="k", private_key_pem=b"not a real pem")
        with self.assertRaises(ob._HaltingError) as ctx:
            ob._sign_orderbook_message(msg, plan, secrets)
        self.assertEqual(ctx.exception.code, ob.OrderBookHaltCode.PRIVATE_KEY_FORMAT_UNSUPPORTED)

    def test_encrypted_key_without_passphrase_support_fails(self):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        encrypted_pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.BestAvailableEncryption(b"pw"),
        )
        plan = _valid_plan()
        msg = ob.build_orderbook_signing_message(plan, "1")
        secrets = ob._EphemeralOrderBookSecrets(api_key_id="k", private_key_pem=encrypted_pem)
        with self.assertRaises(ob._HaltingError) as ctx:
            ob._sign_orderbook_message(msg, plan, secrets)
        self.assertEqual(ctx.exception.code, ob.OrderBookHaltCode.PRIVATE_KEY_FORMAT_UNSUPPORTED)

    def test_non_rsa_key_fails(self):
        from cryptography.hazmat.primitives.asymmetric import ed25519

        key = ed25519.Ed25519PrivateKey.generate()
        pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        plan = _valid_plan()
        msg = ob.build_orderbook_signing_message(plan, "1")
        secrets = ob._EphemeralOrderBookSecrets(api_key_id="k", private_key_pem=pem)
        with self.assertRaises(ob._HaltingError) as ctx:
            ob._sign_orderbook_message(msg, plan, secrets)
        self.assertEqual(ctx.exception.code, ob.OrderBookHaltCode.PRIVATE_KEY_TYPE_UNSUPPORTED)

    def test_signer_rejects_message_bound_to_wrong_plan(self):
        plan_a = _valid_plan(ticker="BTC_USD")
        plan_b = _valid_plan(ticker="ETH_USD")
        msg_for_a = ob.build_orderbook_signing_message(plan_a, "1")
        secrets = ob._EphemeralOrderBookSecrets(api_key_id="k", private_key_pem=_test_rsa_key_pem())
        with self.assertRaises(ob._HaltingError):
            ob._sign_orderbook_message(msg_for_a, plan_b, secrets)

    def test_no_generic_arbitrary_sign_api(self):
        self.assertFalse(hasattr(ob, "sign"))
        self.assertFalse(hasattr(ob, "sign_bytes"))
        self.assertFalse(hasattr(ob, "Signer"))


# ---------------------------------------------------------------------------
# 16.5 Request/transport controls.
# ---------------------------------------------------------------------------


class DnsVerificationTests(unittest.TestCase):
    def test_public_address_accepted(self):
        pairs = ob._classify_dns_answer((_af_candidate(_PUBLIC_ADDR_A),), 443)
        self.assertEqual(pairs, ((4, _PUBLIC_ADDR_A),))

    def test_private_address_rejected(self):
        with self.assertRaises(ob._HaltingError):
            ob._classify_dns_answer((_af_candidate(_PRIVATE_ADDR),), 443)

    def test_mixed_answer_rejects_entire_set(self):
        with self.assertRaises(ob._HaltingError):
            ob._classify_dns_answer((_af_candidate(_PUBLIC_ADDR_A), _af_candidate(_PRIVATE_ADDR)), 443)

    def test_family_version_mismatch_rejected(self):
        with self.assertRaises(ob._HaltingError):
            ob._classify_dns_answer(((socket.AF_INET, ("2600:1234::1", 443, 0, 0)),), 443)

    def test_malformed_sockaddr_rejected(self):
        with self.assertRaises(ob._HaltingError):
            ob._classify_dns_answer(((socket.AF_INET, ("1.2.3.4",)),), 443)

    def test_port_mismatch_rejected(self):
        with self.assertRaises(ob._HaltingError):
            ob._classify_dns_answer(((socket.AF_INET, (_PUBLIC_ADDR_A, 8080)),), 443)

    def test_deterministic_address_selection(self):
        p1 = ob._classify_dns_answer((_af_candidate(_PUBLIC_ADDR_B), _af_candidate(_PUBLIC_ADDR_A)), 443)
        p2 = ob._classify_dns_answer((_af_candidate(_PUBLIC_ADDR_A), _af_candidate(_PUBLIC_ADDR_B)), 443)
        self.assertEqual(p1, p2)
        self.assertEqual(p1[0], (4, _PUBLIC_ADDR_A))

    def test_unsupported_family_rejected(self):
        with self.assertRaises(ob._HaltingError):
            ob._classify_dns_answer(((999, (_PUBLIC_ADDR_A, 443)),), 443)

    def test_empty_answer_rejected(self):
        with self.assertRaises(ob._HaltingError):
            ob._classify_dns_answer((), 443)


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        os.environ[_ACCEPTED_API_KEY_NAME] = "test-key-id-not-a-real-credential"
        os.environ[_ACCEPTED_PEM_NAME] = _test_rsa_key_pem().decode("utf-8")
        self.mp = _MonkeyPatch()

    def tearDown(self):
        os.environ.pop(_ACCEPTED_API_KEY_NAME, None)
        os.environ.pop(_ACCEPTED_PEM_NAME, None)
        self.mp.undo()

    def test_happy_path_produces_snapshot(self):
        plan = _valid_plan()
        _patch_network(self.mp, chunks=[_http_response(200, _valid_orderbook_body())])
        result = ob.execute_demo_authenticated_orderbook(plan)
        self.assertIsInstance(result, ob.KalshiNativeOrderBookSnapshot)
        self.assertEqual(result.market_ticker, "BTC_USD")
        self.assertEqual(result.environment, "KALSHI_DEMO")
        self.assertEqual(result.endpoint_classification, "AUTHENTICATED_READ_ONLY")
        self.assertEqual(result.request_count, 1)
        self.assertEqual(result.retry_count, 0)
        self.assertEqual(result.redirect_count, 0)
        self.assertTrue(result.canonical_snapshot_sha256)
        self.assertEqual(len(result.yes_levels), 2)
        self.assertEqual(len(result.no_levels), 1)

    def test_headers_use_exact_kalshi_access_names(self):
        plan = _valid_plan()
        fake_tls = _patch_network(self.mp, chunks=[_http_response(200, _valid_orderbook_body())])
        result = ob.execute_demo_authenticated_orderbook(plan)
        self.assertIsInstance(result, ob.KalshiNativeOrderBookSnapshot)
        sent = b"".join(fake_tls.sent)
        self.assertIn(b"KALSHI-ACCESS-KEY:", sent)
        self.assertIn(b"KALSHI-ACCESS-SIGNATURE:", sent)
        self.assertIn(b"KALSHI-ACCESS-TIMESTAMP:", sent)
        self.assertNotIn(b"X-KALSHI-", sent)

    def test_one_request_maximum_zero_retries(self):
        plan = _valid_plan()
        _patch_network(self.mp, chunks=[_http_response(200, _valid_orderbook_body())])
        result = ob.execute_demo_authenticated_orderbook(plan)
        self.assertEqual(result.request_count, 1)
        self.assertEqual(result.retry_count, 0)

    def test_production_host_never_resolved(self):
        plan = _valid_plan()
        self.assertEqual(plan.host, "external-api.demo.kalshi.co")
        self.assertNotEqual(plan.host, "external-api.kalshi.com")

    def test_sni_and_host_remain_demo(self):
        plan = _valid_plan()
        fake_tls = _patch_network(self.mp, chunks=[_http_response(200, _valid_orderbook_body())])
        ob.execute_demo_authenticated_orderbook(plan)
        sent = b"".join(fake_tls.sent)
        self.assertIn(b"Host: external-api.demo.kalshi.co", sent)

    def test_tls_failure_halts(self):
        plan = _valid_plan()

        class FailingContext:
            minimum_version = None
            check_hostname = None
            verify_mode = None

            def wrap_socket(self, _sock, server_hostname=None):
                raise ssl.SSLError("certificate verify failed")

        def fake_getaddrinfo(host, port, family, socktype):
            return [(socket.AF_INET, socktype, 0, "", (_PUBLIC_ADDR_A, port))]

        class FakeRawSocket:
            def __init__(self, *_a, **_kw):
                pass

            def settimeout(self, _t):
                pass

            def connect(self, _addr):
                pass

            def close(self):
                pass

        self.mp.setattr(socket, "getaddrinfo", fake_getaddrinfo)
        self.mp.setattr(socket, "socket", FakeRawSocket)
        self.mp.setattr(ssl, "create_default_context", lambda: FailingContext())

        result = ob.execute_demo_authenticated_orderbook(plan)
        self.assertIsInstance(result, ob.OrderBookHalt)
        self.assertEqual(result.code, ob.OrderBookHaltCode.TLS_VERIFICATION_FAILED)

    def test_no_secret_read_before_dns_and_tls(self):
        plan = _valid_plan()
        order = []
        real_getenv = os.environ.get

        def tracking_getenv(name, default=None):
            if name in (_ACCEPTED_API_KEY_NAME, _ACCEPTED_PEM_NAME):
                order.append(("secret", name))
            return real_getenv(name, default)

        self.mp.setattr(os.environ, "get", tracking_getenv)

        def tracking_getaddrinfo(*a, **kw):
            order.append(("dns",))
            return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (_PUBLIC_ADDR_A, a[1]))]

        _patch_network(self.mp, chunks=[_http_response(200, _valid_orderbook_body())])
        self.mp.setattr(socket, "getaddrinfo", tracking_getaddrinfo)

        result = ob.execute_demo_authenticated_orderbook(plan)
        self.assertIsInstance(result, ob.KalshiNativeOrderBookSnapshot)

        dns_index = next(i for i, e in enumerate(order) if e[0] == "dns")
        secret_indices = [i for i, e in enumerate(order) if e[0] == "secret"]
        self.assertTrue(secret_indices)
        self.assertTrue(all(i > dns_index for i in secret_indices))

    def test_credential_missing_reports_no_secret_loaded_lifecycle(self):
        # First secret (api_key_id) missing: nothing was ever loaded.
        plan = _valid_plan()
        os.environ.pop(_ACCEPTED_API_KEY_NAME, None)
        _patch_network(self.mp, chunks=[_http_response(200, _valid_orderbook_body())])
        result = ob.execute_demo_authenticated_orderbook(plan)
        self.assertIsInstance(result, ob.OrderBookHalt)
        self.assertEqual(result.code, ob.OrderBookHaltCode.CREDENTIAL_REFERENCE_MISSING)
        self.assertEqual(result.signature_lifecycle_state, ob.SignatureLifecycleState.NO_SECRET_LOADED)

    def test_second_secret_missing_reports_secret_loaded_no_signature(self):
        # Implementation-04 correction 1: the API-key value was
        # successfully read, but the subsequent private-key read then
        # fails -- the lifecycle must factually report
        # SECRET_LOADED_NO_SIGNATURE, never NO_SECRET_LOADED, because a
        # secret value genuinely was loaded.
        plan = _valid_plan()
        os.environ.pop(_ACCEPTED_PEM_NAME, None)
        _patch_network(self.mp, chunks=[_http_response(200, _valid_orderbook_body())])
        result = ob.execute_demo_authenticated_orderbook(plan)
        self.assertIsInstance(result, ob.OrderBookHalt)
        self.assertEqual(result.code, ob.OrderBookHaltCode.CREDENTIAL_REFERENCE_MISSING)
        self.assertEqual(
            result.signature_lifecycle_state, ob.SignatureLifecycleState.SECRET_LOADED_NO_SIGNATURE
        )

    def test_invalid_private_key_reports_secret_loaded_no_signature(self):
        # Both secrets loaded, but the PEM is malformed: still
        # SECRET_LOADED_NO_SIGNATURE.
        plan = _valid_plan()
        os.environ[_ACCEPTED_PEM_NAME] = "not a real PEM"
        _patch_network(self.mp, chunks=[_http_response(200, _valid_orderbook_body())])
        result = ob.execute_demo_authenticated_orderbook(plan)
        self.assertIsInstance(result, ob.OrderBookHalt)
        self.assertEqual(result.code, ob.OrderBookHaltCode.PRIVATE_KEY_FORMAT_UNSUPPORTED)
        self.assertEqual(
            result.signature_lifecycle_state, ob.SignatureLifecycleState.SECRET_LOADED_NO_SIGNATURE
        )

    def test_send_failure_is_request_result_unknown_send_may_have_begun(self):
        plan = _valid_plan()
        _patch_network(self.mp, raise_on_send=OSError("connection reset"))
        result = ob.execute_demo_authenticated_orderbook(plan)
        self.assertIsInstance(result, ob.OrderBookHalt)
        self.assertEqual(result.code, ob.OrderBookHaltCode.REQUEST_RESULT_UNKNOWN)
        self.assertEqual(result.request_count, 1)
        self.assertEqual(result.retry_count, 0)
        self.assertFalse(result.response_definitively_received)
        self.assertEqual(result.signature_lifecycle_state, ob.SignatureLifecycleState.SEND_MAY_HAVE_BEGUN)

    def test_receive_failure_after_send_is_request_result_unknown(self):
        plan = _valid_plan()
        _patch_network(self.mp, raise_on_recv=socket.timeout("recv timed out"))
        result = ob.execute_demo_authenticated_orderbook(plan)
        self.assertIsInstance(result, ob.OrderBookHalt)
        self.assertEqual(result.code, ob.OrderBookHaltCode.REQUEST_RESULT_UNKNOWN)
        self.assertFalse(result.response_definitively_received)

    def _assert_uncertain_incomplete_response(self, result):
        self.assertIsInstance(result, ob.OrderBookHalt)
        self.assertEqual(result.code, ob.OrderBookHaltCode.REQUEST_RESULT_UNKNOWN)
        self.assertFalse(result.response_definitively_received)
        self.assertEqual(result.signature_lifecycle_state, ob.SignatureLifecycleState.SEND_MAY_HAVE_BEGUN)
        self.assertNotEqual(result.code, ob.OrderBookHaltCode.RESPONSE_JSON_INVALID)
        self.assertNotEqual(
            result.signature_lifecycle_state, ob.SignatureLifecycleState.RESPONSE_DEFINITIVELY_RECEIVED
        )

    def test_eof_before_any_response_byte_is_request_result_unknown(self):
        # Implementation-05 correction 1: clean EOF with zero bytes ever
        # received is uncertain, never a definitive negative outcome.
        plan = _valid_plan()
        _patch_network(self.mp, chunks=[b""])
        result = ob.execute_demo_authenticated_orderbook(plan)
        self._assert_uncertain_incomplete_response(result)

    def test_eof_during_status_line_is_request_result_unknown(self):
        plan = _valid_plan()
        _patch_network(self.mp, chunks=[b"HTTP/1.1 20"])  # cut off mid status line, then EOF
        result = ob.execute_demo_authenticated_orderbook(plan)
        self._assert_uncertain_incomplete_response(result)

    def test_eof_during_headers_is_request_result_unknown(self):
        plan = _valid_plan()
        _patch_network(
            self.mp,
            chunks=[b"HTTP/1.1 200 X\r\nContent-Type: application/json\r\n"],  # no terminating \r\n\r\n
        )
        result = ob.execute_demo_authenticated_orderbook(plan)
        self._assert_uncertain_incomplete_response(result)

    def test_timeout_during_headers_is_request_result_unknown(self):
        plan = _valid_plan()
        _patch_network(
            self.mp,
            chunks=[b"HTTP/1.1 200 X\r\nContent-Type: "],
            raise_on_recv=socket.timeout("timed out mid-headers"),
        )
        # The first recv() call (which returns the partial header chunk)
        # succeeds via the chunk buffer; simulate the timeout by using a
        # fake whose buffer is exhausted after the partial header and
        # whose next recv() call raises.
        result = ob.execute_demo_authenticated_orderbook(plan)
        self._assert_uncertain_incomplete_response(result)

    def test_transport_failure_during_headers_is_request_result_unknown(self):
        plan = _valid_plan()
        _patch_network(
            self.mp,
            chunks=[b"HTTP/1.1 200 X\r\n"],
            raise_on_recv=OSError("connection reset mid-headers"),
        )
        result = ob.execute_demo_authenticated_orderbook(plan)
        self._assert_uncertain_incomplete_response(result)

    def test_response_too_large_lifecycle_is_not_definitively_received(self):
        # Implementation-05 correction 2: RESPONSE_TOO_LARGE remains the
        # correct halt code, but since reception is deliberately stopped
        # before the complete response is established, the evidence must
        # not claim response_definitively_received=True or
        # RESPONSE_DEFINITIVELY_RECEIVED.
        plan = _valid_plan()
        oversized_chunk = b"x" * (ob._MAX_RESPONSE_BYTES + 100)
        header = b"HTTP/1.1 200 X\r\nContent-Type: application/json\r\nContent-Encoding: identity\r\n\r\n"
        _patch_network(self.mp, chunks=[header, oversized_chunk])
        result = ob.execute_demo_authenticated_orderbook(plan)
        self.assertIsInstance(result, ob.OrderBookHalt)
        self.assertEqual(result.code, ob.OrderBookHaltCode.RESPONSE_TOO_LARGE)
        self.assertFalse(result.response_definitively_received)
        self.assertNotEqual(
            result.signature_lifecycle_state, ob.SignatureLifecycleState.RESPONSE_DEFINITIVELY_RECEIVED
        )

    def test_no_automatic_resend_after_unknown(self):
        plan = _valid_plan()
        fake_tls = _patch_network(self.mp, raise_on_send=OSError("reset"))
        ob.execute_demo_authenticated_orderbook(plan)
        self.assertEqual(len(fake_tls.sent), 0)

    def test_status_401_is_authentication_failed(self):
        plan = _valid_plan()
        _patch_network(self.mp, chunks=[_http_response(401, b"{}")])
        result = ob.execute_demo_authenticated_orderbook(plan)
        self.assertEqual(result.code, ob.OrderBookHaltCode.AUTHENTICATION_FAILED)
        self.assertEqual(result.signature_lifecycle_state, ob.SignatureLifecycleState.RESPONSE_DEFINITIVELY_RECEIVED)

    def test_status_403_is_authorization_failed(self):
        plan = _valid_plan()
        _patch_network(self.mp, chunks=[_http_response(403, b"{}")])
        result = ob.execute_demo_authenticated_orderbook(plan)
        self.assertEqual(result.code, ob.OrderBookHaltCode.AUTHORIZATION_OR_PERMISSION_FAILED)

    def test_status_404_is_market_not_found(self):
        plan = _valid_plan()
        _patch_network(self.mp, chunks=[_http_response(404, b"{}")])
        result = ob.execute_demo_authenticated_orderbook(plan)
        self.assertEqual(result.code, ob.OrderBookHaltCode.MARKET_NOT_FOUND)

    def test_status_429_is_rate_limited_no_retry(self):
        plan = _valid_plan()
        _patch_network(self.mp, chunks=[_http_response(429, b"{}")])
        result = ob.execute_demo_authenticated_orderbook(plan)
        self.assertEqual(result.code, ob.OrderBookHaltCode.RATE_LIMITED)
        self.assertEqual(result.retry_count, 0)

    def test_status_5xx_is_unexpected_status(self):
        plan = _valid_plan()
        _patch_network(self.mp, chunks=[_http_response(500, b"{}")])
        result = ob.execute_demo_authenticated_orderbook(plan)
        self.assertEqual(result.code, ob.OrderBookHaltCode.UNEXPECTED_HTTP_STATUS)

    def test_status_3xx_is_redirect_prohibited(self):
        plan = _valid_plan()
        _patch_network(self.mp, chunks=[_http_response(302, b"{}")])
        result = ob.execute_demo_authenticated_orderbook(plan)
        self.assertEqual(result.code, ob.OrderBookHaltCode.ENDPOINT_REDIRECT_PROHIBITED)

    def test_response_encoding_unsupported(self):
        plan = _valid_plan()
        _patch_network(
            self.mp,
            chunks=[_http_response(200, _valid_orderbook_body(), extra_headers="Content-Encoding: gzip\r\n")],
        )
        result = ob.execute_demo_authenticated_orderbook(plan)
        self.assertEqual(result.code, ob.OrderBookHaltCode.RESPONSE_ENCODING_UNSUPPORTED)

    def test_response_content_type_invalid(self):
        plan = _valid_plan()
        _patch_network(self.mp, chunks=[_http_response(200, b"not json", content_type="text/plain")])
        result = ob.execute_demo_authenticated_orderbook(plan)
        self.assertEqual(result.code, ob.OrderBookHaltCode.RESPONSE_CONTENT_TYPE_INVALID)

    def test_response_too_large_enforced_while_receiving(self):
        plan = _valid_plan()
        oversized_chunk = b"x" * (ob._MAX_RESPONSE_BYTES + 100)
        header = b"HTTP/1.1 200 X\r\nContent-Type: application/json\r\nContent-Encoding: identity\r\n\r\n"
        _patch_network(self.mp, chunks=[header, oversized_chunk])
        result = ob.execute_demo_authenticated_orderbook(plan)
        self.assertIsInstance(result, ob.OrderBookHalt)
        self.assertEqual(result.code, ob.OrderBookHaltCode.RESPONSE_TOO_LARGE)

    def _padded_valid_body(self, total_length):
        base = b'{"orderbook_fp":{"yes_dollars":[],"no_dollars":[]}}'
        assert total_length >= len(base)
        pad = total_length - len(base)
        return base[:-1] + b" " * pad + base[-1:]

    def test_body_exactly_65535_succeeds(self):
        plan = _valid_plan()
        body = self._padded_valid_body(65535)
        self.assertEqual(len(body), 65535)
        _patch_network(self.mp, chunks=[_http_response(200, body)])
        result = ob.execute_demo_authenticated_orderbook(plan)
        self.assertIsInstance(result, ob.KalshiNativeOrderBookSnapshot)
        self.assertEqual(result.response_byte_length, 65535)

    def test_body_exactly_65536_succeeds_at_exact_boundary(self):
        # A valid response body of exactly the 65536 cap must not be
        # rejected merely because HTTP headers exist ahead of it.
        plan = _valid_plan()
        body = self._padded_valid_body(65536)
        self.assertEqual(len(body), 65536)
        _patch_network(self.mp, chunks=[_http_response(200, body)])
        result = ob.execute_demo_authenticated_orderbook(plan)
        self.assertIsInstance(result, ob.KalshiNativeOrderBookSnapshot)
        self.assertEqual(result.response_byte_length, 65536)

    def test_body_exactly_65537_rejected(self):
        plan = _valid_plan()
        body = self._padded_valid_body(65537)
        self.assertEqual(len(body), 65537)
        _patch_network(self.mp, chunks=[_http_response(200, body)])
        result = ob.execute_demo_authenticated_orderbook(plan)
        self.assertIsInstance(result, ob.OrderBookHalt)
        self.assertEqual(result.code, ob.OrderBookHaltCode.RESPONSE_TOO_LARGE)

    def test_large_headers_do_not_count_against_body_cap(self):
        # Headers are not counted against the body cap at all -- a large
        # header block preceding a body well below the cap must succeed.
        plan = _valid_plan()
        body = _valid_orderbook_body()
        large_header = (
            b"HTTP/1.1 200 X\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Encoding: identity\r\n"
            + (b"X-Padding: " + b"p" * 60000 + b"\r\n")
            + b"\r\n"
        )
        _patch_network(self.mp, chunks=[large_header + body])
        result = ob.execute_demo_authenticated_orderbook(plan)
        self.assertIsInstance(result, ob.KalshiNativeOrderBookSnapshot)
        self.assertEqual(result.response_byte_length, len(body))

    def test_bounded_read_never_requests_full_4096_near_the_cap(self):
        # Implementation-05 correction 3: once headers are separated and
        # less than 4096 bytes of body capacity remain, the executor
        # must request at most (remaining_capacity + 1) bytes per recv()
        # call -- never an unconditional full 4096.
        plan = _valid_plan()
        header = b"HTTP/1.1 200 X\r\nContent-Type: application/json\r\nContent-Encoding: identity\r\n\r\n"
        body = self._padded_valid_body(65536)
        fake_tls = _patch_network(self.mp, chunks=[header, body])
        result = ob.execute_demo_authenticated_orderbook(plan)
        self.assertIsInstance(result, ob.KalshiNativeOrderBookSnapshot)

        header_len = len(header)
        cap = plan.response_body_cap
        cumulative_returned = 0
        checked_a_bounded_call = False
        for requested, returned in zip(fake_tls.recv_requested_sizes, fake_tls.recv_returned_sizes):
            self.assertLessEqual(requested, 4096)
            body_total_before = max(0, cumulative_returned - header_len)
            remaining_capacity = cap - body_total_before
            if cumulative_returned >= header_len and remaining_capacity < 4096:
                # This call happened during body-phase reception with
                # fewer than 4096 bytes of capacity remaining.
                self.assertLessEqual(requested, remaining_capacity + 1)
                checked_a_bounded_call = True
            cumulative_returned += returned
        self.assertTrue(checked_a_bounded_call, "test did not exercise the near-cap bounded path")

    def test_retained_body_bytes_never_exceed_exactly_65536(self):
        # Implementation-06 correction 2: replaces the Implementation-05
        # test that only measured bytes *read* from the socket (which
        # permitted up to cap+1) -- this instruments
        # _compute_body_retention directly to prove *retained/buffered*
        # bytes never exceed exactly the 65536 cap.
        plan = _valid_plan()
        header = b"HTTP/1.1 200 X\r\nContent-Type: application/json\r\nContent-Encoding: identity\r\n\r\n"
        oversized = b"x" * 200000
        _patch_network(self.mp, chunks=[header, oversized])

        retained_lengths = []
        real_fn = ob._compute_body_retention

        def tracking_fn(body_total, cap, candidate):
            to_retain, new_total, exceeded = real_fn(body_total, cap, candidate)
            retained_lengths.append(len(to_retain))
            return to_retain, new_total, exceeded

        self.mp.setattr(ob, "_compute_body_retention", tracking_fn)
        result = ob.execute_demo_authenticated_orderbook(plan)
        self.assertIsInstance(result, ob.OrderBookHalt)
        self.assertEqual(result.code, ob.OrderBookHaltCode.RESPONSE_TOO_LARGE)

        total_retained = sum(retained_lengths)
        self.assertLessEqual(total_retained, plan.response_body_cap)
        self.assertEqual(total_retained, plan.response_body_cap)

    def test_fake_socket_honors_requested_recv_size(self):
        # Sanity-check the test double itself: recv(n) never returns
        # more than n bytes.
        fake = _FakeSSLSocket(chunks=[b"x" * 10000])
        total = 0
        while True:
            chunk = fake.recv(37)
            if not chunk:
                break
            self.assertLessEqual(len(chunk), 37)
            total += len(chunk)
        self.assertEqual(total, 10000)

    def test_headers_and_body_split_across_arbitrary_chunks(self):
        plan = _valid_plan()
        full_response = _http_response(200, _valid_orderbook_body())
        # Split at several arbitrary byte offsets, including mid-header
        # and mid-body, to prove the incremental header/body split
        # tolerates any chunk boundary.
        offsets = [1, 7, 23, 40, len(full_response) - 5]
        chunks = []
        start = 0
        for off in sorted(offsets):
            if off > start:
                chunks.append(full_response[start:off])
                start = off
        chunks.append(full_response[start:])
        _patch_network(self.mp, chunks=chunks)
        result = ob.execute_demo_authenticated_orderbook(plan)
        self.assertIsInstance(result, ob.KalshiNativeOrderBookSnapshot)

    def test_body_cap_check_happens_before_deadline_slack(self):
        # The hard_cap+8192 slack from Implementation 03 must be gone --
        # confirm the constant no longer exists on the module.
        self.assertFalse(hasattr(ob, "_hard_cap"))

    def test_deadline_exceeded_before_send_is_connectivity_timeout_zero_requests(self):
        plan = _valid_plan()
        with mock.patch("time.monotonic_ns") as mock_time:
            base = 1_000_000_000_000
            mock_time.side_effect = [base] + [base + 20 * 1_000_000_000] * 30
            result = ob.execute_demo_authenticated_orderbook(plan)
        self.assertIsInstance(result, ob.OrderBookHalt)
        self.assertEqual(result.code, ob.OrderBookHaltCode.CONNECTIVITY_TIMEOUT)
        self.assertEqual(result.request_count, 0)

    def test_dns_resolution_failure_halts(self):
        plan = _valid_plan()

        def failing_getaddrinfo(*_a, **_kw):
            raise OSError("DNS unreachable")

        self.mp.setattr(socket, "getaddrinfo", failing_getaddrinfo)
        result = ob.execute_demo_authenticated_orderbook(plan)
        self.assertEqual(result.code, ob.OrderBookHaltCode.DNS_VERIFICATION_FAILED)

    def test_tcp_connect_failure_after_dns_success_is_transport_failure_not_dns(self):
        # Implementation-04 correction 5: a definite pre-send TCP
        # socket/connect failure after DNS has already verified
        # successfully must be TRANSPORT_FAILURE, never
        # DNS_VERIFICATION_FAILED.
        plan = _valid_plan()

        def working_getaddrinfo(host, port, family, socktype):
            return [(socket.AF_INET, socktype, 0, "", (_PUBLIC_ADDR_A, port))]

        class FailingConnectSocket:
            def __init__(self, *_a, **_kw):
                pass

            def settimeout(self, _t):
                pass

            def connect(self, _addr):
                raise OSError("connection refused")

            def close(self):
                pass

        self.mp.setattr(socket, "getaddrinfo", working_getaddrinfo)
        self.mp.setattr(socket, "socket", FailingConnectSocket)

        result = ob.execute_demo_authenticated_orderbook(plan)
        self.assertIsInstance(result, ob.OrderBookHalt)
        self.assertEqual(result.code, ob.OrderBookHaltCode.TRANSPORT_FAILURE)
        self.assertNotEqual(result.code, ob.OrderBookHaltCode.DNS_VERIFICATION_FAILED)

    def test_execution_input_type_invalid(self):
        result = ob.execute_demo_authenticated_orderbook("not a plan")
        self.assertIsInstance(result, ob.OrderBookHalt)


# ---------------------------------------------------------------------------
# Pure body-retention accounting (Implementation-06 correction 2).
# ---------------------------------------------------------------------------


class BodyRetentionTests(unittest.TestCase):
    def test_within_capacity_retains_all(self):
        to_retain, new_total, exceeded = ob._compute_body_retention(0, 100, b"x" * 50)
        self.assertEqual(to_retain, b"x" * 50)
        self.assertEqual(new_total, 50)
        self.assertFalse(exceeded)

    def test_exact_boundary_retains_all(self):
        to_retain, new_total, exceeded = ob._compute_body_retention(0, 100, b"x" * 100)
        self.assertEqual(len(to_retain), 100)
        self.assertEqual(new_total, 100)
        self.assertFalse(exceeded)

    def test_one_byte_over_retains_only_permitted_prefix(self):
        to_retain, new_total, exceeded = ob._compute_body_retention(0, 100, b"x" * 101)
        self.assertEqual(len(to_retain), 100)
        self.assertEqual(new_total, 100)
        self.assertTrue(exceeded)

    def test_far_over_retains_only_permitted_prefix(self):
        to_retain, new_total, exceeded = ob._compute_body_retention(0, 100, b"x" * 5000)
        self.assertEqual(len(to_retain), 100)
        self.assertEqual(new_total, 100)
        self.assertTrue(exceeded)

    def test_zero_remaining_capacity_discards_entire_candidate(self):
        # remaining_capacity == 0: the one-byte (or larger) probe must be
        # discarded entirely, never retained.
        to_retain, new_total, exceeded = ob._compute_body_retention(100, 100, b"x" * 50)
        self.assertEqual(to_retain, b"")
        self.assertEqual(new_total, 100)
        self.assertTrue(exceeded)

    def test_already_exceeded_discards_entire_candidate(self):
        to_retain, new_total, exceeded = ob._compute_body_retention(150, 100, b"x" * 10)
        self.assertEqual(to_retain, b"")
        self.assertEqual(new_total, 150)
        self.assertTrue(exceeded)

    def test_partial_capacity_retains_exact_permitted_bytes(self):
        to_retain, new_total, exceeded = ob._compute_body_retention(90, 100, b"abcdefghij")
        self.assertEqual(to_retain, b"abcdefghij")
        self.assertEqual(new_total, 100)
        self.assertFalse(exceeded)

    def test_partial_capacity_one_byte_over_retains_only_prefix(self):
        to_retain, new_total, exceeded = ob._compute_body_retention(90, 100, b"abcdefghijK")
        self.assertEqual(to_retain, b"abcdefghij")
        self.assertEqual(new_total, 100)
        self.assertTrue(exceeded)

    def test_realistic_cap_boundary(self):
        cap = ob._MAX_RESPONSE_BYTES
        to_retain, new_total, exceeded = ob._compute_body_retention(cap - 1, cap, b"AB")
        self.assertEqual(to_retain, b"A")
        self.assertEqual(new_total, cap)
        self.assertTrue(exceeded)

    def test_never_returns_more_bytes_than_requested_capacity_across_random_sequence(self):
        # Simulate a sequence of arbitrarily-sized incoming chunks and
        # prove cumulative retained bytes never exceed the cap at any
        # point in the sequence.
        cap = 1000
        body_total = 0
        chunk_sizes = [37, 512, 1, 900, 4096, 10, 65536]
        for size in chunk_sizes:
            to_retain, body_total, exceeded = ob._compute_body_retention(body_total, cap, b"x" * size)
            self.assertLessEqual(body_total, cap)
            if exceeded:
                break


# ---------------------------------------------------------------------------
# Five current-value gates (Spec 15.4).
# ---------------------------------------------------------------------------


class CurrentValueGateTests(unittest.TestCase):
    def test_mutated_ticker_rejected(self):
        plan = _valid_plan()
        mutated = replace(plan, market_ticker="DIFFERENT")
        with self.assertRaises(ob._HaltingError):
            ob.require_usable_authenticated_order_book_plan(mutated)

    def test_mutated_host_rejected(self):
        plan = _valid_plan()
        mutated = replace(plan, host="external-api.kalshi.com")
        with self.assertRaises(ob._HaltingError):
            ob.require_usable_authenticated_order_book_plan(mutated)

    def test_mutated_method_rejected(self):
        plan = _valid_plan()
        mutated = replace(plan, method="POST")
        with self.assertRaises(ob._HaltingError):
            ob.require_usable_authenticated_order_book_plan(mutated)

    def test_mutated_retry_count_rejected(self):
        plan = _valid_plan()
        mutated = replace(plan, retry_count=1)
        with self.assertRaises(ob._HaltingError):
            ob.require_usable_authenticated_order_book_plan(mutated)

    def test_mutated_redirects_enabled_rejected(self):
        plan = _valid_plan()
        mutated = replace(plan, redirects_enabled=True)
        with self.assertRaises(ob._HaltingError):
            ob.require_usable_authenticated_order_book_plan(mutated)

    def test_mutated_signing_profile_rejected(self):
        plan = _valid_plan()
        mutated = replace(plan, signing_profile="OTHER")
        with self.assertRaises(ob._HaltingError) as ctx:
            ob.require_usable_authenticated_order_book_plan(mutated)
        self.assertEqual(ctx.exception.code, ob.OrderBookHaltCode.SIGNING_PROFILE_MISMATCH)

    def test_wrong_plan_type_rejected(self):
        with self.assertRaises(ob.OrderBookTypeError):
            ob.require_usable_authenticated_order_book_plan(object())

    def test_plan_never_exposes_secret_fields(self):
        plan = _valid_plan()
        for forbidden in ("private_key", "api_key", "signer", "transport", "client"):
            self.assertFalse(hasattr(plan, forbidden))

    def test_all_five_gate_stages_present_in_stage_enum(self):
        expected = {
            "PRE_DNS_CURRENT_VALUES_REVERIFIED",
            "PRE_SOCKET_CURRENT_VALUES_REVERIFIED",
            "PRE_SECRET_LOAD_CURRENT_VALUES_REVERIFIED",
            "PRE_SIGN_CURRENT_VALUES_REVERIFIED",
            "PRE_SEND_CURRENT_VALUES_REVERIFIED",
        }
        stage_values = {s.value for s in ob.OrderBookStage}
        self.assertTrue(expected.issubset(stage_values))

    # -- Implementation-04 correction 3: every gate must fail closed,
    # never letting a raw AttributeError/TypeError/etc. escape because a
    # previously valid frozen object was subsequently mutated. --

    def test_malformed_capability_envelope_object_fails_closed(self):
        plan = _valid_plan()
        object.__setattr__(plan, "authorization_envelope", object())
        with self.assertRaises(ob._HaltingError):
            ob.require_usable_authenticated_order_book_plan(plan)
        # And the full executor must also never raise -- it must return
        # a deterministic halt.
        result = ob.execute_demo_authenticated_orderbook(plan)
        self.assertIsInstance(result, ob.OrderBookHalt)
        self.assertEqual(result.code, ob.OrderBookHaltCode.EXECUTION_CAPABILITY_NOT_AUTHORIZED)

    def test_malformed_nested_profile_rest_endpoint_fails_closed(self):
        plan = _valid_plan()
        mutated_profile = replace(plan.validated_demo_profile)
        # Replace the nested EndpointComponents with a bare string that
        # has no .scheme/.host/.port/.path attributes at all.
        object.__setattr__(mutated_profile, "rest", "not-an-endpoint-components-object")
        object.__setattr__(plan, "validated_demo_profile", mutated_profile)
        with self.assertRaises(ob._HaltingError):
            ob.require_usable_authenticated_order_book_plan(plan)
        result = ob.execute_demo_authenticated_orderbook(plan)
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_malformed_credential_reference_state_structure_fails_closed(self):
        plan = _valid_plan()
        mutated_profile = replace(plan.validated_demo_profile)
        object.__setattr__(mutated_profile, "credential_reference_states", ("not", "a", "tuple-of-pairs"))
        object.__setattr__(plan, "validated_demo_profile", mutated_profile)
        with self.assertRaises((ob._HaltingError, ob.OrderBookTypeError)):
            ob.require_usable_authenticated_order_book_plan(plan)
        result = ob.execute_demo_authenticated_orderbook(plan)
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_malformed_source_binding_current_value_fails_closed(self):
        plan = _valid_plan()
        object.__setattr__(plan, "source_binding_record_bytes", b"not the accepted record")
        with self.assertRaises(ob._HaltingError):
            ob.require_usable_authenticated_order_book_plan(plan)
        result = ob.execute_demo_authenticated_orderbook(plan)
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_malformed_operation_capability_fails_closed(self):
        plan = _valid_plan()
        object.__setattr__(plan, "operation_capability", "KALSHI_DEMO_AUTHENTICATED_REST_READ")  # plain str, not enum
        with self.assertRaises(ob.OrderBookTypeError):
            ob.require_usable_authenticated_order_book_plan(plan)
        result = ob.execute_demo_authenticated_orderbook(plan)
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_mutated_request_description_and_signing_profile_fail_closed(self):
        plan = _valid_plan()
        object.__setattr__(plan, "full_path", "/trade-api/v2/markets/OTHER/orderbook")
        with self.assertRaises(ob._HaltingError):
            ob.require_usable_authenticated_order_book_plan(plan)
        result = ob.execute_demo_authenticated_orderbook(plan)
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_executor_never_raises_for_any_mutation_category(self):
        # A broad sweep: for every mutation below, execute_demo_authenticated_orderbook
        # must return an OrderBookHalt, never raise.
        mutations = [
            ("authorization_envelope", object()),
            ("operation_capability", "not-an-enum"),
            ("source_binding_record_bytes", b"garbage"),
            ("signing_profile", "WRONG_PROFILE"),
            ("full_path", "/wrong/path"),
        ]
        for field_name, bad_value in mutations:
            with self.subTest(field=field_name):
                plan = _valid_plan()
                object.__setattr__(plan, field_name, bad_value)
                try:
                    result = ob.execute_demo_authenticated_orderbook(plan)
                except Exception as exc:  # pragma: no cover - failure path
                    self.fail(f"raw exception escaped for {field_name}: {exc!r}")
                self.assertIsInstance(result, ob.OrderBookHalt)


# ---------------------------------------------------------------------------
# Complete ValidatedDemoProfile revalidation, including the unused
# WebSocket endpoint (Implementation-05 correction 5). Validating these
# fields never creates or authorizes any WebSocket connection.
# ---------------------------------------------------------------------------


class ProfileCompleteRevalidationTests(unittest.TestCase):
    def _mutated_websocket_profile(self, **ws_overrides):
        base_ws = dict(
            scheme="wss", host="external-api-ws.demo.kalshi.co", port=443,
            path="/trade-api/ws/v2", has_user_info=False, has_query=False, has_fragment=False,
        )
        base_ws.update(ws_overrides)
        return _profile(websocket=EndpointComponents(**base_ws))

    def test_valid_websocket_endpoint_accepted(self):
        plan = ob.plan_demo_authenticated_orderbook(_valid_input(profile=_profile()))
        self.assertIsInstance(plan, ob.AuthenticatedOrderBookPlan)

    def test_mutated_websocket_scheme_rejected(self):
        profile = self._mutated_websocket_profile(scheme="ws")
        result = ob.plan_demo_authenticated_orderbook(_valid_input(profile=profile))
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_production_websocket_host_rejected(self):
        profile = self._mutated_websocket_profile(host="external-api-ws.kalshi.com")
        result = ob.plan_demo_authenticated_orderbook(_valid_input(profile=profile))
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_mutated_websocket_port_rejected(self):
        profile = self._mutated_websocket_profile(port=8080)
        result = ob.plan_demo_authenticated_orderbook(_valid_input(profile=profile))
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_mutated_websocket_path_rejected(self):
        profile = self._mutated_websocket_profile(path="/other/ws/path")
        result = ob.plan_demo_authenticated_orderbook(_valid_input(profile=profile))
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_mutated_websocket_has_user_info_rejected(self):
        profile = self._mutated_websocket_profile(has_user_info=True)
        result = ob.plan_demo_authenticated_orderbook(_valid_input(profile=profile))
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_mutated_websocket_has_query_rejected(self):
        profile = self._mutated_websocket_profile(has_query=True)
        result = ob.plan_demo_authenticated_orderbook(_valid_input(profile=profile))
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_mutated_websocket_has_fragment_rejected(self):
        profile = self._mutated_websocket_profile(has_fragment=True)
        result = ob.plan_demo_authenticated_orderbook(_valid_input(profile=profile))
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_malformed_websocket_type_rejected(self):
        profile = _profile(websocket="not-an-endpoint-components-object")
        result = ob.plan_demo_authenticated_orderbook(_valid_input(profile=profile))
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_wrong_allowlist_revision_rejected(self):
        profile = _profile(allowlist_revision="candidate-01")
        result = ob.plan_demo_authenticated_orderbook(_valid_input(profile=profile))
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_wrong_validation_schema_revision_rejected(self):
        profile = _profile(validation_schema_revision=2)
        result = ob.plan_demo_authenticated_orderbook(_valid_input(profile=profile))
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_validation_schema_revision_wrong_type_rejected(self):
        # An int-valued bool (True == 1) must not silently satisfy an
        # exact-int check.
        profile = _profile(validation_schema_revision=True)
        result = ob.plan_demo_authenticated_orderbook(_valid_input(profile=profile))
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_validating_websocket_endpoint_never_opens_a_connection(self):
        # Validating profile.websocket's current values must never
        # attempt any network activity of any kind.
        with mock.patch("socket.socket", side_effect=AssertionError("no socket allowed")):
            with mock.patch("socket.getaddrinfo", side_effect=AssertionError("no DNS allowed")):
                plan = ob.plan_demo_authenticated_orderbook(_valid_input(profile=_profile()))
        self.assertIsInstance(plan, ob.AuthenticatedOrderBookPlan)

    def test_no_websocket_activity_evidence_anywhere(self):
        plan = _valid_plan()
        for forbidden in ("websocket_connection", "ws_socket", "connect_websocket"):
            self.assertFalse(hasattr(plan, forbidden))


# ---------------------------------------------------------------------------
# Exact EndpointComponents field types (Implementation-06 correction 3).
# A subclass with overridden equality must never impersonate an accepted
# endpoint value.
# ---------------------------------------------------------------------------


class _StrLookalike(str):
    """Claims equality with anything, regardless of actual content."""

    def __eq__(self, other):
        return True

    def __ne__(self, other):
        return False

    def __hash__(self):
        return hash(str(self))


class _IntLookalike(int):
    """Claims equality with anything, regardless of actual value."""

    def __eq__(self, other):
        return True

    def __ne__(self, other):
        return False

    def __hash__(self):
        return hash(int(self))


class EndpointComponentsExactTypeTests(unittest.TestCase):
    def test_lookalike_confirms_it_fools_naive_equality(self):
        # Sanity-check the test doubles themselves: a naive `!=`
        # comparison against the lookalike is fooled.
        lookalike_host = _StrLookalike("evil-host.example.com")
        self.assertFalse(lookalike_host != "external-api.demo.kalshi.co")
        lookalike_port = _IntLookalike(9999)
        self.assertFalse(lookalike_port != 443)

    def test_rest_scheme_lookalike_rejected(self):
        profile = _profile(
            rest=EndpointComponents(
                scheme=_StrLookalike("https"), host="external-api.demo.kalshi.co", port=443,
                path="/trade-api/v2", has_user_info=False, has_query=False, has_fragment=False,
            )
        )
        result = ob.plan_demo_authenticated_orderbook(_valid_input(profile=profile))
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_rest_host_lookalike_rejected(self):
        profile = _profile(
            rest=EndpointComponents(
                scheme="https", host=_StrLookalike("evil-host.example.com"), port=443,
                path="/trade-api/v2", has_user_info=False, has_query=False, has_fragment=False,
            )
        )
        result = ob.plan_demo_authenticated_orderbook(_valid_input(profile=profile))
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_rest_path_lookalike_rejected(self):
        profile = _profile(
            rest=EndpointComponents(
                scheme="https", host="external-api.demo.kalshi.co", port=443,
                path=_StrLookalike("/evil/path"), has_user_info=False, has_query=False, has_fragment=False,
            )
        )
        result = ob.plan_demo_authenticated_orderbook(_valid_input(profile=profile))
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_rest_port_lookalike_rejected(self):
        profile = _profile(
            rest=EndpointComponents(
                scheme="https", host="external-api.demo.kalshi.co", port=_IntLookalike(9999),
                path="/trade-api/v2", has_user_info=False, has_query=False, has_fragment=False,
            )
        )
        result = ob.plan_demo_authenticated_orderbook(_valid_input(profile=profile))
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_rest_port_bool_rejected(self):
        # bool is a subclass of int; type(True) is bool, not int -- must
        # be rejected even though it is numerically falsy/truthy.
        profile = _profile(
            rest=EndpointComponents(
                scheme="https", host="external-api.demo.kalshi.co", port=True,
                path="/trade-api/v2", has_user_info=False, has_query=False, has_fragment=False,
            )
        )
        result = ob.plan_demo_authenticated_orderbook(_valid_input(profile=profile))
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_rest_has_user_info_int_rejected(self):
        # int 0/1 must not silently satisfy an exact-bool check even
        # though 0 == False and 1 == True numerically.
        profile = _profile(
            rest=EndpointComponents(
                scheme="https", host="external-api.demo.kalshi.co", port=443,
                path="/trade-api/v2", has_user_info=0, has_query=False, has_fragment=False,
            )
        )
        result = ob.plan_demo_authenticated_orderbook(_valid_input(profile=profile))
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_rest_has_query_int_rejected(self):
        profile = _profile(
            rest=EndpointComponents(
                scheme="https", host="external-api.demo.kalshi.co", port=443,
                path="/trade-api/v2", has_user_info=False, has_query=0, has_fragment=False,
            )
        )
        result = ob.plan_demo_authenticated_orderbook(_valid_input(profile=profile))
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_rest_has_fragment_int_rejected(self):
        profile = _profile(
            rest=EndpointComponents(
                scheme="https", host="external-api.demo.kalshi.co", port=443,
                path="/trade-api/v2", has_user_info=False, has_query=False, has_fragment=0,
            )
        )
        result = ob.plan_demo_authenticated_orderbook(_valid_input(profile=profile))
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_websocket_scheme_lookalike_rejected(self):
        profile = _profile(
            websocket=EndpointComponents(
                scheme=_StrLookalike("wss"), host="external-api-ws.demo.kalshi.co", port=443,
                path="/trade-api/ws/v2", has_user_info=False, has_query=False, has_fragment=False,
            )
        )
        result = ob.plan_demo_authenticated_orderbook(_valid_input(profile=profile))
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_websocket_host_lookalike_rejected(self):
        profile = _profile(
            websocket=EndpointComponents(
                scheme="wss", host=_StrLookalike("evil-ws-host.example.com"), port=443,
                path="/trade-api/ws/v2", has_user_info=False, has_query=False, has_fragment=False,
            )
        )
        result = ob.plan_demo_authenticated_orderbook(_valid_input(profile=profile))
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_websocket_path_lookalike_rejected(self):
        profile = _profile(
            websocket=EndpointComponents(
                scheme="wss", host="external-api-ws.demo.kalshi.co", port=443,
                path=_StrLookalike("/evil/ws/path"), has_user_info=False, has_query=False, has_fragment=False,
            )
        )
        result = ob.plan_demo_authenticated_orderbook(_valid_input(profile=profile))
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_websocket_port_lookalike_rejected(self):
        profile = _profile(
            websocket=EndpointComponents(
                scheme="wss", host="external-api-ws.demo.kalshi.co", port=_IntLookalike(9999),
                path="/trade-api/ws/v2", has_user_info=False, has_query=False, has_fragment=False,
            )
        )
        result = ob.plan_demo_authenticated_orderbook(_valid_input(profile=profile))
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_websocket_port_bool_rejected(self):
        profile = _profile(
            websocket=EndpointComponents(
                scheme="wss", host="external-api-ws.demo.kalshi.co", port=True,
                path="/trade-api/ws/v2", has_user_info=False, has_query=False, has_fragment=False,
            )
        )
        result = ob.plan_demo_authenticated_orderbook(_valid_input(profile=profile))
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_websocket_has_user_info_int_rejected(self):
        profile = _profile(
            websocket=EndpointComponents(
                scheme="wss", host="external-api-ws.demo.kalshi.co", port=443,
                path="/trade-api/ws/v2", has_user_info=1, has_query=False, has_fragment=False,
            )
        )
        result = ob.plan_demo_authenticated_orderbook(_valid_input(profile=profile))
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_websocket_has_query_int_rejected(self):
        profile = _profile(
            websocket=EndpointComponents(
                scheme="wss", host="external-api-ws.demo.kalshi.co", port=443,
                path="/trade-api/ws/v2", has_user_info=False, has_query=1, has_fragment=False,
            )
        )
        result = ob.plan_demo_authenticated_orderbook(_valid_input(profile=profile))
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_websocket_has_fragment_int_rejected(self):
        profile = _profile(
            websocket=EndpointComponents(
                scheme="wss", host="external-api-ws.demo.kalshi.co", port=443,
                path="/trade-api/ws/v2", has_user_info=False, has_query=False, has_fragment=1,
            )
        )
        result = ob.plan_demo_authenticated_orderbook(_valid_input(profile=profile))
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_direct_helper_rejects_lookalikes(self):
        good = EndpointComponents(
            scheme="https", host="external-api.demo.kalshi.co", port=443,
            path="/trade-api/v2", has_user_info=False, has_query=False, has_fragment=False,
        )
        # Sanity: the exact-type helper accepts a fully-conformant object.
        ob._require_exact_endpoint_component_field_types(good, "test")

        bad_port = EndpointComponents(
            scheme="https", host="external-api.demo.kalshi.co", port=_IntLookalike(443),
            path="/trade-api/v2", has_user_info=False, has_query=False, has_fragment=False,
        )
        with self.assertRaises(ob._HaltingError):
            ob._require_exact_endpoint_component_field_types(bad_port, "test")


# ---------------------------------------------------------------------------
# Source binding (exact accepted record only).
# ---------------------------------------------------------------------------


class SourceBindingTests(unittest.TestCase):
    def test_exact_accepted_record_succeeds(self):
        plan = _valid_plan()
        self.assertEqual(plan.source_binding.effective_auth_classification, "AUTHENTICATED_READ_ONLY")
        self.assertEqual(plan.source_binding.operation_security_key_present, True)

    def test_no_global_security_key_present_field(self):
        # The exact accepted record has no such field; the binding type
        # must not carry it either.
        self.assertFalse(hasattr(ob.OrderBookOperationSourceBinding, "global_security_key_present"))

    def test_no_effective_allows_anonymous_field(self):
        self.assertFalse(hasattr(ob.OrderBookOperationSourceBinding, "effective_allows_anonymous"))

    def test_no_reviewed_base_path_field(self):
        self.assertFalse(hasattr(ob.OrderBookOperationSourceBinding, "reviewed_base_path"))

    def test_hash_mismatch_rejected(self):
        expectation = _expectation(expected_source_binding_record_sha256="f" * 64)
        result = ob.plan_demo_authenticated_orderbook(_valid_input(expectation=expectation))
        self.assertIsInstance(result, ob.OrderBookHalt)
        self.assertEqual(result.code, ob.OrderBookHaltCode.SOURCE_BINDING_MISMATCH)

    def test_wrong_byte_length_rejected(self):
        tampered = _ACCEPTED_RECORD_BYTES + b" "
        result = ob.plan_demo_authenticated_orderbook(_valid_input(record_bytes=tampered))
        self.assertIsInstance(result, ob.OrderBookHalt)
        self.assertEqual(result.code, ob.OrderBookHaltCode.SOURCE_BINDING_MISMATCH)

    def test_tampered_field_rejected(self):
        record = json.loads(_ACCEPTED_RECORD_BYTES)
        record["operation_method"] = "POST"
        tampered_bytes = json.dumps(
            record, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
        ).encode("utf-8")
        tampered_sha = hashlib.sha256(tampered_bytes).hexdigest()
        expectation = _expectation(expected_source_binding_record_sha256=tampered_sha)
        result = ob.plan_demo_authenticated_orderbook(
            _valid_input(record_bytes=tampered_bytes, expectation=expectation)
        )
        self.assertIsInstance(result, ob.OrderBookHalt)
        self.assertEqual(result.code, ob.OrderBookHaltCode.SOURCE_BINDING_MISMATCH)

    def test_bool_vs_int_type_confusion_rejected(self):
        # operation_security_key_present must be exactly bool True, not
        # the numerically-equal int 1.
        record = json.loads(_ACCEPTED_RECORD_BYTES)
        self.assertTrue(ob._strict_json_equal(record, ob._ACCEPTED_BINDING_FIELDS))
        record["operation_security_key_present"] = 1  # int, not bool
        self.assertFalse(ob._strict_json_equal(record, ob._ACCEPTED_BINDING_FIELDS))

    def test_duplicate_key_rejected(self):
        with self.assertRaises(ob.OrderBookError):
            ob._parse_source_binding_record_bytes(b'{"schema_version":1,"schema_version":2}')

    def test_unknown_field_rejected(self):
        record = json.loads(_ACCEPTED_RECORD_BYTES)
        record["unexpected_field"] = "x"
        tampered_bytes = json.dumps(
            record, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
        ).encode("utf-8")
        with self.assertRaises(ob._HaltingError):
            ob._parse_source_binding_record_bytes(tampered_bytes)

    def test_missing_field_rejected(self):
        record = json.loads(_ACCEPTED_RECORD_BYTES)
        del record["retrieved_at_utc"]
        tampered_bytes = json.dumps(
            record, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
        ).encode("utf-8")
        with self.assertRaises(ob._HaltingError):
            ob._parse_source_binding_record_bytes(tampered_bytes)

    def test_placeholder_hash_rejected(self):
        expectation = _expectation(expected_source_binding_record_sha256="0" * 64)
        with self.assertRaises(ob._HaltingError):
            ob.require_usable_execution_dispatch_expectation(expectation)


# ---------------------------------------------------------------------------
# OrderBookExecutionDispatchExpectation (five fields).
# ---------------------------------------------------------------------------


class ExecutionDispatchExpectationTests(unittest.TestCase):
    def test_exact_five_fields(self):
        expectation = _expectation()
        self.assertEqual(expectation.gustavo_execution_authorization_id, "AUTH-OB-03")
        self.assertEqual(expectation.expected_raw_openapi_sha256, _ACCEPTED_RAW_OPENAPI_SHA256)
        self.assertEqual(expectation.expected_source_binding_record_sha256, _ACCEPTED_RECORD_SHA256)
        self.assertEqual(expectation.expected_specification_sha256, _ACCEPTED_SPEC_SHA256)
        self.assertEqual(expectation.expected_implementation_commit, "a" * 40)

    def test_wrong_type_rejected(self):
        with self.assertRaises(ob.OrderBookTypeError):
            ob.require_usable_execution_dispatch_expectation(object())

    def test_blank_authorization_id_rejected(self):
        expectation = _expectation(gustavo_execution_authorization_id="   ")
        with self.assertRaises(ob._HaltingError):
            ob.require_usable_execution_dispatch_expectation(expectation)

    def test_malformed_implementation_commit_rejected(self):
        expectation = _expectation(expected_implementation_commit="not-hex!!")
        with self.assertRaises(ob._HaltingError):
            ob.require_usable_execution_dispatch_expectation(expectation)

    def test_wrong_specification_sha256_rejected(self):
        expectation = _expectation(expected_specification_sha256="b" * 64)
        with self.assertRaises(ob._HaltingError):
            ob.require_usable_execution_dispatch_expectation(expectation)

    def test_wrong_raw_openapi_sha256_rejected(self):
        expectation = _expectation(expected_raw_openapi_sha256="c" * 64)
        with self.assertRaises(ob._HaltingError):
            ob.require_usable_execution_dispatch_expectation(expectation)

    def test_malformed_hash_rejected(self):
        expectation = _expectation(expected_raw_openapi_sha256="not-a-hash")
        with self.assertRaises(ob._HaltingError):
            ob.require_usable_execution_dispatch_expectation(expectation)


# ---------------------------------------------------------------------------
# 16.6 Order-book parser (exact public interface).
# ---------------------------------------------------------------------------


class OrderBookParserTests(unittest.TestCase):
    def _plan(self):
        return _valid_plan()

    def test_valid_two_sided_book(self):
        plan = self._plan()
        body = json.dumps(
            {"orderbook_fp": {"yes_dollars": [["0.5000", "10"]], "no_dollars": [["0.4000", "20"]]}}
        ).encode()
        result = ob.parse_orderbook_response(plan, body, "application/json")
        self.assertIsInstance(result, ob.ParsedNativeOrderBook)
        self.assertEqual(len(result.yes_levels), 1)
        self.assertEqual(len(result.no_levels), 1)

    def test_yes_only_non_empty_no_empty(self):
        plan = self._plan()
        body = json.dumps({"orderbook_fp": {"yes_dollars": [["0.5000", "10"]], "no_dollars": []}}).encode()
        result = ob.parse_orderbook_response(plan, body, "application/json")
        self.assertEqual(len(result.yes_levels), 1)
        self.assertEqual(len(result.no_levels), 0)

    def test_no_only_non_empty_yes_empty(self):
        plan = self._plan()
        body = json.dumps({"orderbook_fp": {"yes_dollars": [], "no_dollars": [["0.4000", "10"]]}}).encode()
        result = ob.parse_orderbook_response(plan, body, "application/json")
        self.assertEqual(len(result.yes_levels), 0)
        self.assertEqual(len(result.no_levels), 1)

    def test_both_empty(self):
        plan = self._plan()
        body = json.dumps({"orderbook_fp": {"yes_dollars": [], "no_dollars": []}}).encode()
        result = ob.parse_orderbook_response(plan, body, "application/json")
        self.assertEqual(len(result.yes_levels), 0)
        self.assertEqual(len(result.no_levels), 0)

    def test_missing_orderbook_fp(self):
        plan = self._plan()
        result = ob.parse_orderbook_response(plan, b"{}", "application/json")
        self.assertIsInstance(result, ob.OrderBookHalt)
        self.assertEqual(result.code, ob.OrderBookHaltCode.ORDER_BOOK_SCHEMA_MALFORMED)

    def test_missing_each_side(self):
        plan = self._plan()
        result = ob.parse_orderbook_response(
            plan, b'{"orderbook_fp": {"yes_dollars": []}}', "application/json"
        )
        self.assertEqual(result.code, ob.OrderBookHaltCode.ORDER_BOOK_SCHEMA_MALFORMED)

    def test_null_side(self):
        plan = self._plan()
        result = ob.parse_orderbook_response(
            plan, b'{"orderbook_fp": {"yes_dollars": null, "no_dollars": []}}', "application/json"
        )
        self.assertEqual(result.code, ob.OrderBookHaltCode.ORDER_BOOK_SCHEMA_MALFORMED)

    def test_wrong_top_level_type(self):
        plan = self._plan()
        result = ob.parse_orderbook_response(plan, b'["not", "object"]', "application/json")
        self.assertEqual(result.code, ob.OrderBookHaltCode.ORDER_BOOK_SCHEMA_MALFORMED)

    def test_wrong_side_type(self):
        plan = self._plan()
        result = ob.parse_orderbook_response(
            plan, b'{"orderbook_fp": {"yes_dollars": "x", "no_dollars": []}}', "application/json"
        )
        self.assertEqual(result.code, ob.OrderBookHaltCode.ORDER_BOOK_SCHEMA_MALFORMED)

    def test_wrong_level_type(self):
        plan = self._plan()
        result = ob.parse_orderbook_response(
            plan,
            b'{"orderbook_fp": {"yes_dollars": [{"price": "0.5", "quantity": "1"}], "no_dollars": []}}',
            "application/json",
        )
        self.assertEqual(result.code, ob.OrderBookHaltCode.ORDER_BOOK_LEVEL_MALFORMED)

    def test_duplicate_json_keys_at_every_depth(self):
        plan = self._plan()
        result = ob.parse_orderbook_response(
            plan,
            b'{"orderbook_fp": {"yes_dollars": [], "no_dollars": [], "yes_dollars": []}}',
            "application/json",
        )
        self.assertEqual(result.code, ob.OrderBookHaltCode.RESPONSE_DUPLICATE_JSON_KEY)

    def test_duplicate_json_key_nested_inside_orderbook_fp(self):
        plan = self._plan()
        result = ob.parse_orderbook_response(
            plan,
            b'{"orderbook_fp": {"no_dollars": [], "no_dollars": [], "yes_dollars": []}}',
            "application/json",
        )
        self.assertEqual(result.code, ob.OrderBookHaltCode.RESPONSE_DUPLICATE_JSON_KEY)

    def test_json_nan_rejected_exact_code(self):
        # Implementation-06 correction 4: NaN must classify as
        # RESPONSE_JSON_INVALID, never RESPONSE_DUPLICATE_JSON_KEY.
        plan = self._plan()
        result = ob.parse_orderbook_response(
            plan, b'{"orderbook_fp": {"yes_dollars": [[NaN, "1"]], "no_dollars": []}}', "application/json"
        )
        self.assertIsInstance(result, ob.OrderBookHalt)
        self.assertEqual(result.code, ob.OrderBookHaltCode.RESPONSE_JSON_INVALID)
        self.assertNotEqual(result.code, ob.OrderBookHaltCode.RESPONSE_DUPLICATE_JSON_KEY)

    def test_json_infinity_rejected_exact_code(self):
        plan = self._plan()
        result = ob.parse_orderbook_response(
            plan, b'{"orderbook_fp": {"yes_dollars": [["0.5", Infinity]], "no_dollars": []}}', "application/json"
        )
        self.assertIsInstance(result, ob.OrderBookHalt)
        self.assertEqual(result.code, ob.OrderBookHaltCode.RESPONSE_JSON_INVALID)
        self.assertNotEqual(result.code, ob.OrderBookHaltCode.RESPONSE_DUPLICATE_JSON_KEY)

    def test_json_negative_infinity_rejected_exact_code(self):
        plan = self._plan()
        result = ob.parse_orderbook_response(
            plan, b'{"orderbook_fp": {"yes_dollars": [["0.5", -Infinity]], "no_dollars": []}}', "application/json"
        )
        self.assertIsInstance(result, ob.OrderBookHalt)
        self.assertEqual(result.code, ob.OrderBookHaltCode.RESPONSE_JSON_INVALID)
        self.assertNotEqual(result.code, ob.OrderBookHaltCode.RESPONSE_DUPLICATE_JSON_KEY)

    def test_reject_json_constant_raises_distinct_exception_type(self):
        with self.assertRaises(ob._InvalidJsonConstantError):
            ob._reject_json_constant("NaN")

    def test_reject_duplicate_keys_raises_distinct_exception_type(self):
        with self.assertRaises(ob._DuplicateJsonKeyError):
            ob._reject_duplicate_keys([("a", 1), ("a", 2)])

    def test_duplicate_key_and_nan_never_conflated(self):
        # Both defects present simultaneously: the earlier-encountered
        # one wins deterministically, but neither is ever misreported as
        # the other's code.
        plan = self._plan()
        dup_first = ob.parse_orderbook_response(
            plan,
            b'{"orderbook_fp": {"yes_dollars": [], "yes_dollars": [[NaN, "1"]], "no_dollars": []}}',
            "application/json",
        )
        self.assertIn(
            dup_first.code,
            (ob.OrderBookHaltCode.RESPONSE_DUPLICATE_JSON_KEY, ob.OrderBookHaltCode.RESPONSE_JSON_INVALID),
        )

    def test_bool_as_number_cannot_pass(self):
        plan = self._plan()
        result = ob.parse_orderbook_response(
            plan, b'{"orderbook_fp": {"yes_dollars": [[true, "1"]], "no_dollars": []}}', "application/json"
        )
        self.assertEqual(result.code, ob.OrderBookHaltCode.ORDER_BOOK_PRICE_INVALID)

    def test_malformed_numeric_string(self):
        plan = self._plan()
        result = ob.parse_orderbook_response(
            plan, b'{"orderbook_fp": {"yes_dollars": [["abc", "1"]], "no_dollars": []}}', "application/json"
        )
        self.assertEqual(result.code, ob.OrderBookHaltCode.ORDER_BOOK_PRICE_INVALID)

    def test_exponent_rejected(self):
        plan = self._plan()
        result = ob.parse_orderbook_response(
            plan, b'{"orderbook_fp": {"yes_dollars": [["5e-1", "1"]], "no_dollars": []}}', "application/json"
        )
        self.assertEqual(result.code, ob.OrderBookHaltCode.ORDER_BOOK_PRICE_INVALID)

    def test_sign_rejected(self):
        plan = self._plan()
        result = ob.parse_orderbook_response(
            plan, b'{"orderbook_fp": {"yes_dollars": [["-0.5000", "1"]], "no_dollars": []}}', "application/json"
        )
        self.assertEqual(result.code, ob.OrderBookHaltCode.ORDER_BOOK_PRICE_INVALID)

    def test_whitespace_rejected(self):
        plan = self._plan()
        result = ob.parse_orderbook_response(
            plan, b'{"orderbook_fp": {"yes_dollars": [[" 0.5000", "1"]], "no_dollars": []}}', "application/json"
        )
        self.assertEqual(result.code, ob.OrderBookHaltCode.ORDER_BOOK_PRICE_INVALID)

    def test_over_four_price_decimals_rejected(self):
        plan = self._plan()
        result = ob.parse_orderbook_response(
            plan, b'{"orderbook_fp": {"yes_dollars": [["0.12345", "1"]], "no_dollars": []}}', "application/json"
        )
        self.assertEqual(result.code, ob.OrderBookHaltCode.ORDER_BOOK_PRICE_INVALID)

    def test_over_two_quantity_decimals_rejected(self):
        plan = self._plan()
        result = ob.parse_orderbook_response(
            plan, b'{"orderbook_fp": {"yes_dollars": [["0.5000", "1.234"]], "no_dollars": []}}', "application/json"
        )
        self.assertEqual(result.code, ob.OrderBookHaltCode.ORDER_BOOK_QUANTITY_INVALID)

    def test_price_outside_range_rejected(self):
        plan = self._plan()
        result = ob.parse_orderbook_response(
            plan, b'{"orderbook_fp": {"yes_dollars": [["1.5000", "1"]], "no_dollars": []}}', "application/json"
        )
        self.assertEqual(result.code, ob.OrderBookHaltCode.ORDER_BOOK_PRICE_INVALID)

    def test_zero_quantity_rejected(self):
        plan = self._plan()
        result = ob.parse_orderbook_response(
            plan, b'{"orderbook_fp": {"yes_dollars": [["0.5000", "0"]], "no_dollars": []}}', "application/json"
        )
        self.assertEqual(result.code, ob.OrderBookHaltCode.ORDER_BOOK_QUANTITY_INVALID)

    def test_negative_quantity_rejected(self):
        plan = self._plan()
        result = ob.parse_orderbook_response(
            plan, b'{"orderbook_fp": {"yes_dollars": [["0.5000", "-1"]], "no_dollars": []}}', "application/json"
        )
        self.assertEqual(result.code, ob.OrderBookHaltCode.ORDER_BOOK_QUANTITY_INVALID)

    def test_duplicate_price_rejected(self):
        plan = self._plan()
        result = ob.parse_orderbook_response(
            plan,
            b'{"orderbook_fp": {"yes_dollars": [["0.5000", "1"], ["0.5000", "2"]], "no_dollars": []}}',
            "application/json",
        )
        self.assertEqual(result.code, ob.OrderBookHaltCode.ORDER_BOOK_DUPLICATE_PRICE)

    def test_wire_order_permutation_reconstructs_same_ladder(self):
        plan = self._plan()
        body_a = json.dumps(
            {"orderbook_fp": {"yes_dollars": [["0.6000", "1"], ["0.5000", "2"]], "no_dollars": []}}
        ).encode()
        body_b = json.dumps(
            {"orderbook_fp": {"yes_dollars": [["0.5000", "2"], ["0.6000", "1"]], "no_dollars": []}}
        ).encode()
        result_a = ob.parse_orderbook_response(plan, body_a, "application/json")
        result_b = ob.parse_orderbook_response(plan, body_b, "application/json")
        self.assertEqual(
            [(l.price, l.quantity) for l in result_a.yes_levels],
            [(l.price, l.quantity) for l in result_b.yes_levels],
        )

    def test_unknown_top_level_field_rejected(self):
        plan = self._plan()
        result = ob.parse_orderbook_response(
            plan,
            b'{"orderbook_fp": {"yes_dollars": [], "no_dollars": []}, "ticker": "SPOOFED"}',
            "application/json",
        )
        self.assertEqual(result.code, ob.OrderBookHaltCode.ORDER_BOOK_SCHEMA_SHAPE_CHANGED)

    def test_unknown_orderbook_fp_field_rejected(self):
        plan = self._plan()
        result = ob.parse_orderbook_response(
            plan,
            b'{"orderbook_fp": {"yes_dollars": [], "no_dollars": [], "future_field": 1}}',
            "application/json",
        )
        self.assertEqual(result.code, ob.OrderBookHaltCode.ORDER_BOOK_SCHEMA_SHAPE_CHANGED)

    def test_simultaneous_legacy_and_current_schema_rejected(self):
        plan = self._plan()
        result = ob.parse_orderbook_response(
            plan,
            b'{"orderbook": {"yes": [], "no": []}, "orderbook_fp": {"yes_dollars": [], "no_dollars": []}}',
            "application/json",
        )
        self.assertEqual(result.code, ob.OrderBookHaltCode.ORDER_BOOK_SCHEMA_SHAPE_CHANGED)

    def test_response_too_large(self):
        plan = self._plan()
        body = b"x" * (plan.response_body_cap + 1)
        result = ob.parse_orderbook_response(plan, body, "application/json")
        self.assertEqual(result.code, ob.OrderBookHaltCode.RESPONSE_TOO_LARGE)


class NoRawJsonParserExceptionTests(unittest.TestCase):
    """Implementation-06 correction 5: no raw ValueError/OverflowError/
    RecursionError/parser-implementation exception may escape
    parse_orderbook_response() for a response within the accepted
    65536-byte cap."""

    def _plan(self):
        return _valid_plan()

    def test_integer_token_at_conversion_limit_does_not_raise(self):
        # A JSON integer literal long enough to trip Python's
        # integer-string-conversion limit (default 4300 digits), well
        # within the 65536-byte cap.
        plan = self._plan()
        huge_int = b"9" * 4400
        body = b'{"orderbook_fp": {"yes_dollars": [[' + huge_int + b', "1"]], "no_dollars": []}}'
        self.assertLessEqual(len(body), plan.response_body_cap)
        try:
            result = ob.parse_orderbook_response(plan, body, "application/json")
        except Exception as exc:  # pragma: no cover - failure path
            self.fail(f"raw exception escaped: {exc!r}")
        self.assertIsInstance(result, ob.OrderBookHalt)
        self.assertEqual(result.code, ob.OrderBookHaltCode.RESPONSE_JSON_INVALID)

    def test_integer_token_in_unknown_field_does_not_raise(self):
        # The huge integer sits inside a field that would ordinarily be
        # rejected as unknown -- but json.loads() itself must not raise
        # before schema validation ever runs.
        plan = self._plan()
        huge_int = b"1" * 5000
        body = (
            b'{"orderbook_fp": {"yes_dollars": [], "no_dollars": [], "extra": ' + huge_int + b"}}"
        )
        self.assertLessEqual(len(body), plan.response_body_cap)
        try:
            result = ob.parse_orderbook_response(plan, body, "application/json")
        except Exception as exc:  # pragma: no cover - failure path
            self.fail(f"raw exception escaped: {exc!r}")
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_deeply_nested_json_does_not_raise_recursion_error(self):
        # Deep enough nesting to trigger Python's/json's recursion limit
        # in this environment (empirically ~10000 with the C-accelerated
        # scanner), still well within the 65536-byte cap.
        plan = self._plan()
        depth = 15000
        body = (
            b'{"orderbook_fp": {"yes_dollars": [], "no_dollars": [], "x":'
            + b"[" * depth
            + b"]" * depth
            + b"}}"
        )
        self.assertLessEqual(len(body), plan.response_body_cap)
        try:
            result = ob.parse_orderbook_response(plan, body, "application/json")
        except Exception as exc:  # pragma: no cover - failure path
            self.fail(f"raw exception escaped: {exc!r}")
        self.assertIsInstance(result, ob.OrderBookHalt)
        self.assertEqual(result.code, ob.OrderBookHaltCode.RESPONSE_JSON_INVALID)

    def test_deeply_nested_json_in_level_position_does_not_raise(self):
        plan = self._plan()
        depth = 15000
        body = (
            b'{"orderbook_fp": {"yes_dollars": [[' + b"[" * depth + b"]" * depth + b', "1"]], "no_dollars": []}}'
        )
        self.assertLessEqual(len(body), plan.response_body_cap)
        try:
            result = ob.parse_orderbook_response(plan, body, "application/json")
        except Exception as exc:  # pragma: no cover - failure path
            self.fail(f"raw exception escaped: {exc!r}")
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_malformed_utf8_does_not_raise(self):
        plan = self._plan()
        body = b"\xff\xfe\x00invalid utf-8"
        try:
            result = ob.parse_orderbook_response(plan, body, "application/json")
        except Exception as exc:  # pragma: no cover - failure path
            self.fail(f"raw exception escaped: {exc!r}")
        self.assertIsInstance(result, ob.OrderBookHalt)
        self.assertEqual(result.code, ob.OrderBookHaltCode.RESPONSE_JSON_INVALID)

    def test_malformed_json_syntax_does_not_raise(self):
        plan = self._plan()
        body = b'{"orderbook_fp": {"yes_dollars": [}'
        try:
            result = ob.parse_orderbook_response(plan, body, "application/json")
        except Exception as exc:  # pragma: no cover - failure path
            self.fail(f"raw exception escaped: {exc!r}")
        self.assertIsInstance(result, ob.OrderBookHalt)
        self.assertEqual(result.code, ob.OrderBookHaltCode.RESPONSE_JSON_INVALID)

    def test_empty_body_does_not_raise(self):
        plan = self._plan()
        try:
            result = ob.parse_orderbook_response(plan, b"", "application/json")
        except Exception as exc:  # pragma: no cover - failure path
            self.fail(f"raw exception escaped: {exc!r}")
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_truncated_json_does_not_raise(self):
        plan = self._plan()
        body = b'{"orderbook_fp": {"yes_dollars": [["0.5"'
        try:
            result = ob.parse_orderbook_response(plan, body, "application/json")
        except Exception as exc:  # pragma: no cover - failure path
            self.fail(f"raw exception escaped: {exc!r}")
        self.assertIsInstance(result, ob.OrderBookHalt)


class OrderBookParserCurrentValueGateTests(unittest.TestCase):
    """Implementation-05 correction 4: `parse_orderbook_response` itself
    revalidates the complete current plan at entry -- a mutated plan
    must not be able to widen the response body cap, host/environment,
    operation capability, source binding, ticker/path binding,
    query/body policy, signing profile, or request/retry/redirect
    policy."""

    def _valid_body(self):
        return json.dumps({"orderbook_fp": {"yes_dollars": [], "no_dollars": []}}).encode()

    def test_valid_plan_succeeds(self):
        plan = _valid_plan()
        result = ob.parse_orderbook_response(plan, self._valid_body(), "application/json")
        self.assertIsInstance(result, ob.ParsedNativeOrderBook)

    def test_widened_response_body_cap_rejected(self):
        plan = _valid_plan()
        mutated = replace(plan, response_body_cap=999999999)
        result = ob.parse_orderbook_response(mutated, self._valid_body(), "application/json")
        self.assertIsInstance(result, ob.OrderBookHalt)
        self.assertNotIsInstance(result, ob.ParsedNativeOrderBook)

    def test_mutated_host_rejected(self):
        plan = _valid_plan()
        mutated = replace(plan, host="external-api.kalshi.com")
        result = ob.parse_orderbook_response(mutated, self._valid_body(), "application/json")
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_mutated_operation_capability_rejected(self):
        plan = _valid_plan()
        object.__setattr__(plan, "operation_capability", "not-an-enum")
        result = ob.parse_orderbook_response(plan, self._valid_body(), "application/json")
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_mutated_source_binding_rejected(self):
        plan = _valid_plan()
        mutated = replace(plan, source_binding_record_bytes=b"garbage")
        result = ob.parse_orderbook_response(mutated, self._valid_body(), "application/json")
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_mutated_ticker_path_binding_rejected(self):
        plan = _valid_plan()
        mutated = replace(plan, full_path="/trade-api/v2/markets/OTHER/orderbook")
        result = ob.parse_orderbook_response(mutated, self._valid_body(), "application/json")
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_mutated_query_policy_rejected(self):
        plan = _valid_plan()
        mutated = replace(plan, query_policy="INCLUDE_DEPTH")
        result = ob.parse_orderbook_response(mutated, self._valid_body(), "application/json")
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_mutated_body_policy_rejected(self):
        plan = _valid_plan()
        mutated = replace(plan, body_policy="PRESENT")
        result = ob.parse_orderbook_response(mutated, self._valid_body(), "application/json")
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_mutated_signing_profile_rejected(self):
        plan = _valid_plan()
        mutated = replace(plan, signing_profile="OTHER_PROFILE")
        result = ob.parse_orderbook_response(mutated, self._valid_body(), "application/json")
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_mutated_retry_count_rejected(self):
        plan = _valid_plan()
        mutated = replace(plan, retry_count=1)
        result = ob.parse_orderbook_response(mutated, self._valid_body(), "application/json")
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_mutated_redirects_enabled_rejected(self):
        plan = _valid_plan()
        mutated = replace(plan, redirects_enabled=True)
        result = ob.parse_orderbook_response(mutated, self._valid_body(), "application/json")
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_mutated_request_budget_rejected(self):
        plan = _valid_plan()
        mutated = replace(plan, request_budget=2)
        result = ob.parse_orderbook_response(mutated, self._valid_body(), "application/json")
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_wrong_plan_type_rejected(self):
        result = ob.parse_orderbook_response("not a plan", self._valid_body(), "application/json")
        self.assertIsInstance(result, ob.OrderBookHalt)

    def test_parser_never_raises_raw_exception_for_any_mutation(self):
        mutations = [
            ("response_body_cap", 999999999),
            ("host", "external-api.kalshi.com"),
            ("full_path", "/trade-api/v2/markets/OTHER/orderbook"),
            ("query_policy", "BAD"),
            ("signing_profile", "BAD"),
            ("source_binding_record_bytes", b"garbage"),
            ("retry_count", 5),
        ]
        for field_name, bad_value in mutations:
            with self.subTest(field=field_name):
                plan = _valid_plan()
                object.__setattr__(plan, field_name, bad_value)
                try:
                    result = ob.parse_orderbook_response(plan, self._valid_body(), "application/json")
                except Exception as exc:  # pragma: no cover - failure path
                    self.fail(f"raw exception escaped for {field_name}: {exc!r}")
                self.assertIsInstance(result, ob.OrderBookHalt)


# ---------------------------------------------------------------------------
# 12.6 Content-Type policy.
# ---------------------------------------------------------------------------


class ContentTypePolicyTests(unittest.TestCase):
    def test_bare_application_json_accepted(self):
        ob._parse_content_type("application/json")  # no raise

    def test_charset_utf8_accepted_case_insensitive(self):
        ob._parse_content_type("application/json; charset=UTF-8")
        ob._parse_content_type("Application/JSON; Charset=utf-8")

    def test_wrong_media_type_rejected(self):
        with self.assertRaises(ob._HaltingError):
            ob._parse_content_type("text/plain")

    def test_other_parameter_rejected(self):
        with self.assertRaises(ob._HaltingError):
            ob._parse_content_type("application/json; boundary=x")

    def test_duplicate_charset_rejected(self):
        with self.assertRaises(ob._HaltingError):
            ob._parse_content_type("application/json; charset=utf-8; charset=utf-8")

    def test_conflicting_charset_rejected(self):
        with self.assertRaises(ob._HaltingError):
            ob._parse_content_type("application/json; charset=utf-16")

    def test_no_content_sniffing(self):
        # A wrong declared media type is rejected even though the body
        # would parse fine as JSON -- content sniffing never overrides it.
        with self.assertRaises(ob._HaltingError):
            ob._parse_content_type("text/html")


# ---------------------------------------------------------------------------
# Snapshot canonicalization / identity.
# ---------------------------------------------------------------------------


class SnapshotTests(unittest.TestCase):
    def _snapshot(self, **overrides):
        fields = dict(
            environment="KALSHI_DEMO", market_ticker="X", method="GET",
            route_template="/markets/{ticker}/orderbook",
            full_request_path="/trade-api/v2/markets/X/orderbook",
            endpoint_classification="AUTHENTICATED_READ_ONLY",
            request_timestamp_ms=1000, request_started_monotonic_ns=0, request_completed_monotonic_ns=1,
            yes_levels=(ob.KalshiNativeOrderBookLevel(decimal.Decimal("0.5"), decimal.Decimal("10")),),
            no_levels=(), canonical_level_ordering="PRICE_ASCENDING",
            response_byte_length=10, response_sha256="a" * 64,
            raw_openapi_sha256=_ACCEPTED_RAW_OPENAPI_SHA256,
            source_binding_record_sha256=_ACCEPTED_RECORD_SHA256,
            request_count=1, retry_count=0, redirect_count=0,
            gustavo_execution_authorization_id="A", expected_implementation_commit="a" * 40,
            specification_sha256=_ACCEPTED_SPEC_SHA256,
        )
        fields.update(overrides)
        return ob.KalshiNativeOrderBookSnapshot(**fields)

    def test_canonical_serialization_uses_decimal_strings(self):
        snap = self._snapshot()
        canonical = snap.serialize_canonical()
        self.assertIn(b'"0.5000"', canonical)
        self.assertIn(b'"10.00"', canonical)

    def test_identical_snapshots_same_identity(self):
        snap1 = self._snapshot().with_canonical_identity()
        snap2 = self._snapshot().with_canonical_identity()
        self.assertEqual(snap1.canonical_snapshot_sha256, snap2.canonical_snapshot_sha256)

    def test_different_ticker_changes_identity(self):
        snap1 = self._snapshot(market_ticker="X").with_canonical_identity()
        snap2 = self._snapshot(market_ticker="Y", full_request_path="/trade-api/v2/markets/Y/orderbook").with_canonical_identity()
        self.assertNotEqual(snap1.canonical_snapshot_sha256, snap2.canonical_snapshot_sha256)

    def test_different_request_started_monotonic_ns_changes_identity(self):
        # Implementation-04 correction 6: timing evidence must be bound
        # into the canonical identity.
        snap1 = self._snapshot(request_started_monotonic_ns=0).with_canonical_identity()
        snap2 = self._snapshot(request_started_monotonic_ns=12345).with_canonical_identity()
        self.assertNotEqual(snap1.canonical_snapshot_sha256, snap2.canonical_snapshot_sha256)

    def test_different_request_completed_monotonic_ns_changes_identity(self):
        snap1 = self._snapshot(request_completed_monotonic_ns=1).with_canonical_identity()
        snap2 = self._snapshot(request_completed_monotonic_ns=99999).with_canonical_identity()
        self.assertNotEqual(snap1.canonical_snapshot_sha256, snap2.canonical_snapshot_sha256)

    def test_canonical_dict_contains_timing_fields(self):
        snap = self._snapshot()
        canonical = snap._canonical_dict()
        self.assertIn("request_started_monotonic_ns", canonical)
        self.assertIn("request_completed_monotonic_ns", canonical)

    def test_specification_sha256_present_and_bound_to_identity(self):
        snap1 = self._snapshot(specification_sha256=_ACCEPTED_SPEC_SHA256).with_canonical_identity()
        snap2 = self._snapshot(specification_sha256="f" * 64).with_canonical_identity()
        self.assertEqual(snap1.specification_sha256, _ACCEPTED_SPEC_SHA256)
        self.assertNotEqual(snap1.canonical_snapshot_sha256, snap2.canonical_snapshot_sha256)

    def test_no_api_key_or_secret_field_exists(self):
        snap = self._snapshot()
        for forbidden in ("api_key_id", "private_key", "signature", "auth_header"):
            self.assertFalse(hasattr(snap, forbidden))


# ---------------------------------------------------------------------------
# Context-independent Decimal canonicalization (Implementation-06
# correction 6). Quantities far larger than the default 28-digit Decimal
# context precision must canonicalize exactly, without rounding, without
# an invented magnitude cap, and without decimal.InvalidOperation.
# ---------------------------------------------------------------------------


class LargeDecimalCanonicalizationTests(unittest.TestCase):
    _HUGE_QUANTITY = "9" * 40 + ".99"  # 42 significant digits >> default prec 28

    def test_default_context_precision_is_exceeded_by_fixture(self):
        # Sanity-check the fixture itself actually exceeds the ambient
        # default context precision, so this test is meaningful.
        self.assertGreater(len(self._HUGE_QUANTITY.replace(".", "")), decimal.getcontext().prec)

    def test_safe_quantize_succeeds_for_huge_quantity(self):
        value = decimal.Decimal(self._HUGE_QUANTITY)
        try:
            result = ob._safe_quantize(value, decimal.Decimal("0.01"))
        except decimal.InvalidOperation as exc:
            self.fail(f"decimal.InvalidOperation escaped: {exc!r}")
        self.assertEqual(str(result), self._HUGE_QUANTITY)

    def test_safe_quantize_does_not_touch_ambient_context(self):
        original_prec = decimal.getcontext().prec
        value = decimal.Decimal(self._HUGE_QUANTITY)
        ob._safe_quantize(value, decimal.Decimal("0.01"))
        self.assertEqual(decimal.getcontext().prec, original_prec)

    def test_level_construction_succeeds_with_huge_quantity(self):
        level = ob.KalshiNativeOrderBookLevel(
            price=decimal.Decimal("0.5000"), quantity=decimal.Decimal(self._HUGE_QUANTITY)
        )
        try:
            canonical_qty = level.canonical_quantity_str()
        except decimal.InvalidOperation as exc:
            self.fail(f"decimal.InvalidOperation escaped: {exc!r}")
        self.assertEqual(canonical_qty, self._HUGE_QUANTITY)

    def test_parser_accepts_huge_quantity_in_response_body(self):
        plan = _valid_plan()
        body = (
            b'{"orderbook_fp": {"yes_dollars": [["0.5000", "'
            + self._HUGE_QUANTITY.encode("ascii")
            + b'"]], "no_dollars": []}}'
        )
        self.assertLessEqual(len(body), plan.response_body_cap)
        try:
            result = ob.parse_orderbook_response(plan, body, "application/json")
        except decimal.InvalidOperation as exc:
            self.fail(f"decimal.InvalidOperation escaped: {exc!r}")
        self.assertIsInstance(result, ob.ParsedNativeOrderBook)
        self.assertEqual(len(result.yes_levels), 1)
        self.assertEqual(str(result.yes_levels[0].quantity), self._HUGE_QUANTITY)

    def test_snapshot_construction_succeeds_with_huge_quantity(self):
        level = ob.KalshiNativeOrderBookLevel(
            price=decimal.Decimal("0.5000"), quantity=decimal.Decimal(self._HUGE_QUANTITY)
        )
        snapshot = ob.KalshiNativeOrderBookSnapshot(
            environment="KALSHI_DEMO", market_ticker="X", method="GET",
            route_template="/markets/{ticker}/orderbook",
            full_request_path="/trade-api/v2/markets/X/orderbook",
            endpoint_classification="AUTHENTICATED_READ_ONLY",
            request_timestamp_ms=1000, request_started_monotonic_ns=0, request_completed_monotonic_ns=1,
            yes_levels=(level,), no_levels=(), canonical_level_ordering="PRICE_ASCENDING",
            response_byte_length=10, response_sha256="a" * 64,
            raw_openapi_sha256=_ACCEPTED_RAW_OPENAPI_SHA256,
            source_binding_record_sha256=_ACCEPTED_RECORD_SHA256,
            request_count=1, retry_count=0, redirect_count=0,
            gustavo_execution_authorization_id="A", expected_implementation_commit="a" * 40,
            specification_sha256=_ACCEPTED_SPEC_SHA256,
        )
        try:
            with_identity = snapshot.with_canonical_identity()
        except decimal.InvalidOperation as exc:
            self.fail(f"decimal.InvalidOperation escaped: {exc!r}")
        self.assertTrue(with_identity.canonical_snapshot_sha256)
        self.assertEqual(len(with_identity.canonical_snapshot_sha256), 64)
        canonical_bytes = with_identity.serialize_canonical()
        self.assertIn(self._HUGE_QUANTITY.encode("ascii"), canonical_bytes)

    def test_no_invented_upper_magnitude_limit_in_quantity_grammar(self):
        # The accepted quantity lexical grammar itself imposes no digit
        # count ceiling.
        self.assertIsNotNone(ob._QUANTITY_STRING_PATTERN.fullmatch("9" * 100 + ".99"))

    def test_moderately_large_price_also_safe(self):
        # Price is capped to [0, 1] by the accepted grammar, so this
        # mainly proves the safe-quantize path is exercised uniformly;
        # scale is still bounded to 4 decimals as required.
        value = decimal.Decimal("0." + "9" * 4)
        result = ob._safe_quantize(value, decimal.Decimal("0.0001"))
        self.assertEqual(str(result), "0.9999")


# ---------------------------------------------------------------------------
# Evidence and non-capabilities (16.7).
# ---------------------------------------------------------------------------


class EvidenceAndNonCapabilityTests(unittest.TestCase):
    def test_halt_repr_never_contains_secret_material(self):
        halt = ob._halt(
            ob.OrderBookHaltCode.PRIVATE_KEY_FORMAT_UNSUPPORTED,
            ob.OrderBookStage.SECRETS_LOADED,
            signature_lifecycle_state=ob.SignatureLifecycleState.SECRET_LOADED_NO_SIGNATURE,
        )
        text = repr(halt)
        self.assertNotIn("BEGIN PRIVATE KEY", text)
        self.assertNotIn("KALSHI-ACCESS-SIGNATURE", text)

    def test_module_exposes_no_generic_client(self):
        self.assertFalse(hasattr(ob, "KalshiClient"))
        self.assertFalse(hasattr(ob, "HttpClient"))

    def test_module_has_no_websocket_or_order_surface(self):
        for forbidden in ("connect_websocket", "place_order", "cancel_order", "amend_order", "fund_account"):
            self.assertFalse(hasattr(ob, forbidden))

    def test_planning_performs_no_network_access(self):
        with mock.patch("socket.socket", side_effect=AssertionError("no socket allowed")):
            with mock.patch("socket.getaddrinfo", side_effect=AssertionError("no DNS allowed")):
                plan = ob.plan_demo_authenticated_orderbook(_valid_input())
        self.assertIsInstance(plan, ob.AuthenticatedOrderBookPlan)

    def test_ticker_grammar(self):
        self.assertTrue(ob.validate_ticker_grammar("BTC_USD"))
        self.assertFalse(ob.validate_ticker_grammar("BTC USD"))
        self.assertFalse(ob.validate_ticker_grammar(""))
        self.assertFalse(ob.validate_ticker_grammar("A" * 201))
        self.assertTrue(ob.validate_ticker_grammar("A" * 200))


# ---------------------------------------------------------------------------
# Expected/observed halt evidence (Spec 7.5, Implementation-05
# correction 7).
# ---------------------------------------------------------------------------


class ExpectedObservedHaltEvidenceTests(unittest.TestCase):
    def setUp(self):
        os.environ[_ACCEPTED_API_KEY_NAME] = "test-key-id-not-a-real-credential"
        os.environ[_ACCEPTED_PEM_NAME] = _test_rsa_key_pem().decode("utf-8")
        self.mp = _MonkeyPatch()

    def tearDown(self):
        os.environ.pop(_ACCEPTED_API_KEY_NAME, None)
        os.environ.pop(_ACCEPTED_PEM_NAME, None)
        self.mp.undo()

    def test_absent_where_not_applicable(self):
        # A ticker-grammar rejection has no natural expected/observed
        # pair -- both must be absent (None), not populated with
        # invented values.
        result = ob.plan_demo_authenticated_orderbook(_valid_input(ticker="bad ticker"))
        self.assertIsInstance(result, ob.OrderBookHalt)
        self.assertIsNone(result.expected)
        self.assertIsNone(result.observed)

    def test_capability_permitted_expected_observed(self):
        envelope = _envelope(network_access=AV.PROHIBITED)
        result = ob.plan_demo_authenticated_orderbook(_valid_input(envelope=envelope))
        self.assertIsInstance(result, ob.OrderBookHalt)
        self.assertEqual(result.expected, "PERMITTED")
        self.assertEqual(result.observed, "PROHIBITED")

    def test_prohibited_capability_expected_observed(self):
        envelope = _envelope(demo_writes=AV.PERMITTED)
        result = ob.plan_demo_authenticated_orderbook(_valid_input(envelope=envelope))
        self.assertIsInstance(result, ob.OrderBookHalt)
        self.assertEqual(result.expected, "PROHIBITED")
        self.assertEqual(result.observed, "PERMITTED")

    def test_http_status_expected_observed(self):
        plan = _valid_plan()
        _patch_network(self.mp, chunks=[_http_response(404, b"{}")])
        result = ob.execute_demo_authenticated_orderbook(plan)
        self.assertIsInstance(result, ob.OrderBookHalt)
        self.assertEqual(result.code, ob.OrderBookHaltCode.MARKET_NOT_FOUND)
        self.assertEqual(result.expected, "200")
        self.assertEqual(result.observed, "404")

    def test_http_status_500_expected_observed(self):
        plan = _valid_plan()
        _patch_network(self.mp, chunks=[_http_response(500, b"{}")])
        result = ob.execute_demo_authenticated_orderbook(plan)
        self.assertIsInstance(result, ob.OrderBookHalt)
        self.assertEqual(result.expected, "200")
        self.assertEqual(result.observed, "500")

    def test_expected_observed_only_safe_closed_values(self):
        # Every populated expected/observed value across a representative
        # sweep of halts must be one of a small set of safe, closed
        # classification strings -- never free-form or secret-shaped.
        safe_values = {"PERMITTED", "PROHIBITED", "200", "401", "403", "404", "429", "500"}

        cases = []
        envelope_permitted_violation = _envelope(credential_use=AV.PROHIBITED)
        cases.append(ob.plan_demo_authenticated_orderbook(_valid_input(envelope=envelope_permitted_violation)))
        envelope_prohibited_violation = _envelope(production_writes=AV.PERMITTED)
        cases.append(ob.plan_demo_authenticated_orderbook(_valid_input(envelope=envelope_prohibited_violation)))

        for result in cases:
            self.assertIsInstance(result, ob.OrderBookHalt)
            if result.expected is not None:
                self.assertIn(result.expected, safe_values)
            if result.observed is not None:
                self.assertIn(result.observed, safe_values)

    def test_expected_observed_never_contain_secret_shaped_content(self):
        plan = _valid_plan()
        os.environ[_ACCEPTED_PEM_NAME] = "not a real PEM -----BEGIN PRIVATE KEY----- fake"
        _patch_network(self.mp, chunks=[_http_response(200, _valid_orderbook_body())])
        result = ob.execute_demo_authenticated_orderbook(plan)
        self.assertIsInstance(result, ob.OrderBookHalt)
        for field_value in (result.expected, result.observed, result.detail):
            if field_value is not None:
                self.assertNotIn("BEGIN PRIVATE KEY", field_value)
                self.assertNotIn("not a real PEM", field_value)

    def test_expected_observed_never_contain_raw_exception_text(self):
        # A malformed capability envelope object triggers the canonical
        # validator's own exception internally -- the resulting halt's
        # expected/observed/detail must never echo that raw exception
        # message verbatim.
        plan = _valid_plan()
        object.__setattr__(plan, "authorization_envelope", object())
        result = ob.execute_demo_authenticated_orderbook(plan)
        self.assertIsInstance(result, ob.OrderBookHalt)
        for field_value in (result.expected, result.observed, result.detail):
            if field_value is not None:
                self.assertNotIn("CapabilityEnvelopeTypeError", field_value)
                self.assertNotIn("Traceback", field_value)


if __name__ == "__main__":
    unittest.main()
