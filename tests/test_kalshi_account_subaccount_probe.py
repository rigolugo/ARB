"""Deterministic offline acceptance tests for the Kalshi Demo Route-B B1
account/subaccount capability-and-facts probe.

Covers B1-TEST-001 through B1-TEST-012 of
``KALSHI_DEMO_ROUTE_B_B1_ACCOUNT_SUBACCOUNT_CAPABILITY_AND_FACTS_SPEC_01.md``
and adds explicit regression coverage for correction findings C01-01 (global /
per-request deadline lifecycle), C01-02 (the bounded response-acquisition
transport boundary), C01-03 (evidence output root external to the repository),
and C01-04 (lexical, not Decimal-equivalent, balance duplicate identity).

Every test is fully offline: fake clocks, a fake transport that establishes
response metadata only and hands the B1 runner a bounded
:class:`ResponseBodyReader` it drives itself, an injected fake signer (plus
one synthetic RSA key on a temporary path for the real signing boundary),
synthetic JSON, and synthetic credential material.
Nothing here performs DNS, opens a socket, performs TLS, makes an HTTP request,
reads a real credential value, or contacts Kalshi.
"""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import inspect
import json
import re
from pathlib import Path

import pytest

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from arb.venues.kalshi import account_subaccount_probe as m


# ---------------------------------------------------------------------------
# Deterministic fakes.
# ---------------------------------------------------------------------------


class FakeClock:
    """Monotonic time advances only via :meth:`advance_ms` (default step 0),
    so deadline crossings are exact and reproducible."""

    def __init__(
        self,
        *,
        start_ns: int = 0,
        step_ns: int = 0,
        unix_ms: int = 1_724_800_000_000,
        utc: str = "2026-08-27T20:10:00Z",
    ) -> None:
        self._mono = start_ns
        self._step = step_ns
        self._unix_ms = unix_ms
        self._utc = utc
        self.monotonic_calls = 0

    def monotonic_ns(self) -> int:
        self.monotonic_calls += 1
        value = self._mono
        self._mono += self._step
        return value

    def advance_ms(self, ms: int) -> None:
        self._mono += ms * 1_000_000

    def unix_millis(self) -> int:
        return self._unix_ms

    def now_utc_rfc3339(self) -> str:
        return self._utc


class OrderRecordingClock(FakeClock):
    """Records the order of monotonic vs wall-clock reads so a test can prove
    the global deadline is anchored (a monotonic read) before any other
    boundary work such as run-state construction (a wall-clock read)."""

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self.events: list[str] = []

    def monotonic_ns(self) -> int:
        self.events.append("mono")
        return super().monotonic_ns()

    def now_utc_rfc3339(self) -> str:
        self.events.append("wall")
        return super().now_utc_rfc3339()


class FakeSigner:
    """Returns fixed, unmistakably synthetic signature bytes."""

    def __init__(self, signature: bytes = b"\x01\x02\x03\x04" * 16) -> None:
        self._signature = signature
        self.messages: list[bytes] = []

    def sign(self, message_bytes: bytes) -> bytes:
        self.messages.append(bytes(message_bytes))
        return self._signature


class SlowSigner(FakeSigner):
    """A signer whose key-preparation/signing step consumes monotonic time.
    Used to prove signing is charged to the *global* budget only and never to
    the per-request network budget (C01-01)."""

    def __init__(self, clock: FakeClock, advance_ms: int, **kw) -> None:
        super().__init__(**kw)
        self._clock = clock
        self._advance_ms = advance_ms

    def sign(self, message_bytes: bytes) -> bytes:
        self._clock.advance_ms(self._advance_ms)
        return super().sign(message_bytes)


@dataclasses.dataclass
class Scripted:
    """One scripted transport response for :class:`ScriptedTransport`."""

    status: int = 200
    headers: tuple = (("Content-Type", "application/json"),)
    body: bytes = b"{}"
    kind: str = "RESPONSE"          # or "TIMEOUT" / "TRANSPORT_ERROR"
    pre_ms: int = 0                 # clock advance before the transport returns
    per_chunk_ms: int = 0          # clock advance on each B1-owned reader.read
    read_size: int | None = None  # cap the fake reader serves per read
    error_detail: str | None = None
    close_ms: int = 0             # clock advance inside the B1-driven reader.close (C03-01-C)


class ScriptReader:
    """A B1-driven bounded response-body reader (C02-02).

    The B1 runner -- not this reader and not the transport -- owns the read
    loop. Each :meth:`read` serves at most ``min(max_bytes, read_size)``
    bytes, never more than the caller asked for, records every
    ``(max_bytes, timeout_ms)`` pair B1 passes in, and optionally advances a
    fake clock so deadline-crossing-between-reads can be exercised.
    """

    def __init__(self, body: bytes, *, clock=None, per_read_ms: int = 0,
                 read_size: int | None = None, close_ms: int = 0) -> None:
        self._body = bytes(body)
        self._pos = 0
        self._clock = clock
        self._per_read_ms = per_read_ms
        self._read_size = read_size
        self._close_ms = close_ms
        self.calls: list[tuple[int, int]] = []
        self.close_calls: list[int] = []
        self.closed = False

    def read(self, max_bytes: int, timeout_ms: int) -> bytes:
        assert isinstance(max_bytes, int) and max_bytes > 0, max_bytes
        assert isinstance(timeout_ms, int) and timeout_ms > 0, timeout_ms
        self.calls.append((max_bytes, timeout_ms))
        if self._clock is not None and self._per_read_ms:
            self._clock.advance_ms(self._per_read_ms)
        take = max_bytes if self._read_size is None else min(max_bytes, self._read_size)
        piece = self._body[self._pos : self._pos + take]
        self._pos += len(piece)
        return piece

    def close(self, timeout_ms: int) -> None:
        # C03-01-C: B1 only calls close with a finite, positive remaining
        # budget; it never calls close once no positive budget remains.
        assert isinstance(timeout_ms, int) and timeout_ms > 0, timeout_ms
        self.close_calls.append(timeout_ms)
        self.closed = True
        if self._clock is not None and self._close_ms:
            self._clock.advance_ms(self._close_ms)


def resp(
    obj=None,
    *,
    status: int = 200,
    content_type: str | None = "application/json",
    extra_headers: tuple = (),
    raw_body: bytes | None = None,
    chunk_size: int | None = None,
    **scripted_kw,
) -> Scripted:
    body = raw_body if raw_body is not None else json.dumps(obj).encode("utf-8")
    headers: list[tuple[str, str]] = []
    if content_type is not None:
        headers.append(("Content-Type", content_type))
    headers.extend(extra_headers)
    return Scripted(
        status=status,
        headers=tuple(headers),
        body=body,
        read_size=chunk_size,
        **scripted_kw,
    )


class ScriptedTransport:
    """Serves a scripted response per operation label. It establishes status +
    headers only and hands B1 a :class:`ScriptReader`; it never reads,
    materialises, or returns body bytes (C02-02). The B1 runner drives every
    blocking ``reader.read`` itself.
    """

    def __init__(self, clock: FakeClock, script: dict) -> None:
        self._clock = clock
        self._script = script
        self.calls: list[str] = []
        # C03-01-A: every (operation_label, timeout_ms) budget B1 hands to
        # perform, in call order.
        self.perform_timeouts: list[tuple[str, int]] = []
        self.readers: dict[str, ScriptReader] = {}

    def perform(self, request, timeout_ms):
        # C03-01-A: perform structurally receives the B1-computed finite,
        # positive remainder of the effective min(per-request, global) budget.
        assert isinstance(timeout_ms, int) and 0 < timeout_ms <= m.PER_REQUEST_DEADLINE_MS, (
            timeout_ms
        )
        self.calls.append(request.operation_label)
        self.perform_timeouts.append((request.operation_label, timeout_ms))
        entry = self._script[request.operation_label]
        if not isinstance(entry, Scripted):  # pragma: no cover - defensive
            raise AssertionError("script entries must be Scripted instances")
        if entry.pre_ms:
            self._clock.advance_ms(entry.pre_ms)
        if entry.kind == "TIMEOUT":
            return m.TransportResponse(kind="TIMEOUT")
        if entry.kind == "TRANSPORT_ERROR":
            return m.TransportResponse(
                kind="TRANSPORT_ERROR", error_detail=entry.error_detail or "err"
            )
        reader = ScriptReader(
            entry.body,
            clock=self._clock,
            per_read_ms=entry.per_chunk_ms,
            read_size=entry.read_size,
            close_ms=entry.close_ms,
        )
        self.readers[request.operation_label] = reader
        return m.TransportResponse(
            kind="RESPONSE",
            status=entry.status,
            headers=entry.headers,
            reader=reader,
        )


# ---------------------------------------------------------------------------
# Response / fixture helpers.
# ---------------------------------------------------------------------------

CURRENT_KEY_ID = "SYNTHETIC_CURRENT_KEY_ID"
UNRELATED_KEY_ID = "SYNTHETIC_OTHER_KEY_ID"
UNRELATED_KEY_NAME = "synthetic-other-key-name"
PRIVATE_KEY_PATH_VALUE = "/synthetic/vault/kalshi_demo_key.pem"


def account_limits_body(usage_tier: str = "advanced") -> dict:
    return {
        "usage_tier": usage_tier,
        "read": {"refill_rate": 10, "bucket_capacity": 100},
        "write": {"refill_rate": 5, "bucket_capacity": 50},
        "grants": [
            {
                "exchange_instance": "event_contract",
                "level": "standard",
                "source": "account_grant",
                "expires_ts": None,
            },
            {
                "exchange_instance": "margined",
                "level": "standard",
                "source": "account_grant",
            },
        ],
    }


def api_keys_body(*, subaccount=m._ABSENT, include_subaccount_null=False) -> dict:
    element = {
        "api_key_id": CURRENT_KEY_ID,
        "name": "synthetic-current-key",
        "scopes": ["read", "write"],
    }
    if include_subaccount_null:
        element["subaccount"] = None
    elif subaccount is not m._ABSENT:
        element["subaccount"] = subaccount
    return {
        "api_keys": [
            {
                "api_key_id": UNRELATED_KEY_ID,
                "name": UNRELATED_KEY_NAME,
                "scopes": ["read"],
                "subaccount": 7,
            },
            element,
        ]
    }


def balances_body(rows) -> dict:
    return {"subaccount_balances": list(rows)}


def netting_body(rows) -> dict:
    return {"netting_configs": list(rows)}


def brow(sub, idx=0, balance="0", ts=1) -> dict:
    return {
        "subaccount_number": sub,
        "exchange_index": idx,
        "balance": balance,
        "updated_ts": ts,
    }


def nrow(sub, idx=0, enabled=True) -> dict:
    return {"subaccount_number": sub, "enabled": enabled, "exchange_index": idx}


def make_env(**overrides) -> dict:
    env = {
        m.API_KEY_ID_ENV: CURRENT_KEY_ID,
        m.PRIVATE_KEY_PATH_ENV: PRIVATE_KEY_PATH_VALUE,
    }
    env.update(overrides)
    return env


# --- Correction-02 task-current source fixtures ---------------------------
#
# The accepted task-current OpenAPI 3.29.0 raw source is
# LOCAL_ONLY_EXTERNAL_SOURCE_EVIDENCE (325930 bytes, sha256 99bdf4...); no Git
# blob identity is asserted for those raw bytes (corrected dispatch S.3/S.5).
CURRENT_OPENAPI_RAW_SHA256 = (
    "99bdf4093d7eced607ba8b48cc99e3da862c35d99afa2a0c0f63f14eab9237ed"
)
CURRENT_OPENAPI_RAW_BYTES = 325930
CURRENT_OPENAPI_SOURCE_URL = "https://docs.kalshi.com/openapi.yaml"
HISTORICAL_3280_SHA256 = (
    "cb853ffc47262646b96bba7b1a8925c9c344128fd498cdaa8dbcf9a0b3b8211b"
)
AUTHORING_RECORD_SHA256 = (
    "964056df0d633fa27d53363aa58ee3c59c2fc6281c0b1cc68f25bbad5b104dc2"
)
AUTHORING_BINDING_NAME = "KALSHI_DEMO_ROUTE_B_B1_OFFICIAL_RENDERED_SOURCE_BINDING_01"
CURRENT_OPENAPI_BINDING_NAME = (
    "KALSHI_DEMO_ROUTE_B_B1_CURRENT_OFFICIAL_OPENAPI_SOURCE_BINDING_01"
)

# N05: the canonical report/checkpoint does NOT establish the empirical
# observation time of the 3.29.0 source. This value is SYNTHETIC, test-only,
# and must never be presented as the empirical 3.29.0 observation. It is
# deliberately an implausible historic instant so it cannot be mistaken for a
# real 2026 observation.
SYNTHETIC_TEST_ONLY_OBSERVED_AT = "2000-01-01T00:00:00Z"

# The fabricated empirical timestamp the blocked predecessor used for the
# 3.29.0 source. Built by concatenation so this file never contains the
# forbidden literal verbatim (see N05 self-scan tests).
_FORBIDDEN_FABRICATED_TS = "2026-08-28" + "T00:00:00Z"


def current_openapi_binding(
    *, observed_at_utc: str = SYNTHETIC_TEST_ONLY_OBSERVED_AT, **overrides
) -> m.SourceEvidenceBinding:
    """A non-authoring :class:`SourceEvidenceBinding` for the accepted OpenAPI
    3.29.0 task-current source. ``observed_at_utc`` is synthetic test data
    (see :data:`SYNTHETIC_TEST_ONLY_OBSERVED_AT`)."""

    base = dict(
        name=CURRENT_OPENAPI_BINDING_NAME,
        source_url=CURRENT_OPENAPI_SOURCE_URL,
        raw_source_bytes=CURRENT_OPENAPI_RAW_BYTES,
        raw_source_sha256=CURRENT_OPENAPI_RAW_SHA256,
        openapi_format="3.0.0",
        openapi_info_version="3.29.0",
        observed_at_utc=observed_at_utc,
        fresh_raw_openapi_status="OBTAINED_LOCAL_ONLY_EXTERNAL_SOURCE_EVIDENCE",
        historical_openapi_context_sha256=HISTORICAL_3280_SHA256,
    )
    base.update(overrides)
    return m.SourceEvidenceBinding(**base)


def current_openapi_source(
    *, semantics: str = "UNRESTRICTED", record_label: str = "TASK_CURRENT_OPENAPI_3_29_0_FIXTURE",
    binding: m.SourceEvidenceBinding | None = None, **record_overrides,
) -> m.TaskCurrentSourceRecord:
    """A valid non-authoring task-current source record bound to the OpenAPI
    3.29.0 evidence. Its active ``source_binding_record_sha256`` is the
    deterministic canonical-binding-record hash (Correction 02 / BIND-01)."""

    rec = dataclasses.replace(
        m.authoring_task_current_source_record(),
        api_keys_absent_subaccount_semantics=semantics,
        evidence_binding=binding if binding is not None else current_openapi_binding(),
        record_label=record_label,
    )
    if record_overrides:
        rec = dataclasses.replace(rec, **record_overrides)
    return rec


def unrestricted_source() -> m.TaskCurrentSourceRecord:
    """A valid non-authoring task-current source that explicitly defines the
    GET /api_keys absent/null subaccount response as UNRESTRICTED."""

    return current_openapi_source(semantics="UNRESTRICTED")


def not_exposed_source() -> m.TaskCurrentSourceRecord:
    """The accepted authoring-legacy binding: NOT_EXPOSED absent/null
    semantics, congruent with the accepted authoring source binding."""

    return m.authoring_task_current_source_record()


def authoring_emitted_identity() -> m.EmittedSourceBindingIdentity:
    """The resolved emitted identity for the accepted authoring-congruent
    record (name / 964056df... / 2026-08-27T20:02:16Z / ...)."""

    return m._emitted_source_binding(m.authoring_task_current_source_record())


def run_probe(script, *, env=None, source=None, clock=None, signer=None, output_root=None):
    clock = clock or FakeClock()
    transport = ScriptedTransport(clock, script)
    result = m.execute_b1_account_subaccount_probe(
        credentials_env=env if env is not None else make_env(),
        source_record=source or unrestricted_source(),
        transport=transport,
        signer=signer or FakeSigner(),
        clock=clock,
    )
    # C02-01 evidence-write boundary: persistence is a separate, explicit step
    # after the execute boundary returns -- never inside it.
    if output_root is not None:
        result.write_evidence(output_root)
    return result, transport


def full_discovery_script(*, numbered=(2,), api_keys=None):
    balances = [brow(0, balance="0")] + [brow(n, balance="1.25") for n in numbered]
    netting = [nrow(0)] + [nrow(n, enabled=False) for n in numbered]
    return {
        m.OP_ACCOUNT_LIMITS: resp(account_limits_body()),
        m.OP_API_KEYS: resp(api_keys or api_keys_body(include_subaccount_null=True)),
        m.OP_SUBACCOUNT_BALANCES: resp(balances_body(balances)),
        m.OP_SUBACCOUNT_NETTING: resp(netting_body(netting)),
    }


def drive_read(body, *, per_read_ms=0, read_size=None, total_prior=0,
               effective_deadline_ns=10 ** 18, clock=None):
    """Drive the B1-owned :func:`_read_response_body` loop directly with a
    :class:`ScriptReader`. Returns ``(body_bytes, reader, clock)``."""

    clock = clock or FakeClock()
    reader = ScriptReader(body, clock=clock, per_read_ms=per_read_ms,
                          read_size=read_size)
    data = m._read_response_body(
        reader,
        clock=clock,
        effective_deadline_ns=effective_deadline_ns,
        total_prior=total_prior,
    )
    return data, reader, clock


# ===========================================================================
# B1-TEST-001 -- base/path/method/capability containment.
# ===========================================================================


class TestB1Test001Containment:
    def test_exact_demo_target_accepted(self):
        assert m.is_permitted_b1_target(
            "https://external-api.demo.kalshi.co/trade-api/v2/account/limits"
        )
        for label in m.OPERATION_LABELS:
            assert m.is_permitted_b1_target(
                "https://external-api.demo.kalshi.co" + m.OP_FULL_PATHS[label]
            )

    def test_compatibility_demo_host_rejected(self):
        assert not m.is_permitted_b1_target(
            "https://demo-api.kalshi.co/trade-api/v2/account/limits"
        )
        with pytest.raises(m.CapabilityScopeViolation):
            m.evaluate_request_target(
                scheme="https",
                host="demo-api.kalshi.co",
                port=443,
                path="/trade-api/v2/account/limits",
                method="GET",
            )

    def test_production_hosts_rejected(self):
        for host in ("api.elections.kalshi.com", "trading-api.kalshi.com", "api.kalshi.com"):
            assert not m.is_permitted_b1_target(
                f"https://{host}/trade-api/v2/account/limits"
            )

    def test_non_https_and_non_443_rejected(self):
        assert not m.is_permitted_b1_target(
            "http://external-api.demo.kalshi.co/trade-api/v2/account/limits"
        )
        assert not m.is_permitted_b1_target(
            "https://external-api.demo.kalshi.co:8443/trade-api/v2/account/limits"
        )

    def test_query_fragment_userinfo_rejected(self):
        base = "https://external-api.demo.kalshi.co/trade-api/v2/account/limits"
        assert not m.is_permitted_b1_target(base + "?x=1")
        assert not m.is_permitted_b1_target(base + "#frag")
        assert not m.is_permitted_b1_target(
            "https://user:pw@external-api.demo.kalshi.co/trade-api/v2/account/limits"
        )

    def test_only_four_get_paths_accepted(self):
        assert m.ALLOWED_FULL_PATHS == frozenset(m.OP_FULL_PATHS.values())
        assert len(m.ALLOWED_FULL_PATHS) == 4
        assert not m.is_permitted_b1_target(
            "https://external-api.demo.kalshi.co/trade-api/v2/portfolio/subaccounts/transfers"
        )
        assert not m.is_permitted_b1_target(
            "https://external-api.demo.kalshi.co/trade-api/v2/account/limits/../orders"
        )

    def test_non_get_methods_rejected_before_send(self):
        for method in ("POST", "DELETE", "PATCH", "PUT"):
            assert not m.is_permitted_b1_target(
                "https://external-api.demo.kalshi.co/trade-api/v2/account/limits",
                method,
            )
            with pytest.raises(m.CapabilityScopeViolation):
                m.evaluate_request_target(
                    scheme="https",
                    host=m.DEMO_HOST,
                    port=443,
                    path=m.OP_FULL_PATHS[m.OP_ACCOUNT_LIMITS],
                    method=method,
                )
        with pytest.raises(m.CapabilityScopeViolation):
            m.RequestPlan(
                sequence=1,
                operation_label=m.OP_ACCOUNT_LIMITS,
                method="POST",
                scheme="https",
                host=m.DEMO_HOST,
                port=443,
                full_path=m.OP_FULL_PATHS[m.OP_ACCOUNT_LIMITS],
                base_path=m.OP_BASE_PATHS[m.OP_ACCOUNT_LIMITS],
            )

    def test_redirect_disabled_and_3xx_not_followed(self):
        clock = FakeClock()
        script = {
            m.OP_ACCOUNT_LIMITS: resp(
                None,
                status=302,
                content_type=None,
                extra_headers=(("Location", "https://evil.example/x"),),
                raw_body=b"",
            )
        }
        result, transport = run_probe(script, clock=clock)
        assert result.terminal_outcome == m.B1TerminalOutcome.B1_SOURCE_DRIFT
        assert len(transport.calls) == 1  # no second request to the redirect target
        assert result.manifest.request_count == 1
        assert result.manifest.requests[0].status_class == m.RequestStatusClass.REDIRECT_3XX

    def test_request_count_cannot_exceed_four(self):
        assert m.MAX_REQUEST_COUNT == 4
        assert len(m.build_request_plan_sequence()) == 4
        result, transport = run_probe(full_discovery_script())
        assert len(transport.calls) == 4
        assert result.manifest.request_count == 4

    def test_no_websocket_or_network_client_in_module(self):
        source = Path(m.__file__).read_text(encoding="utf-8")
        lowered = source.lower()
        for needle in ("wss://", "ws://", "websocket", "import socket", "import ssl",
                       "http.client", "httpx", "urllib.request", "import requests"):
            assert needle not in lowered, f"module unexpectedly references {needle!r}"

    def test_no_redirect_retry_fallback_constants(self):
        assert m.MAX_REDIRECT_COUNT == 0
        assert m.AUTOMATIC_RETRY_COUNT == 0
        assert m.MAX_ATTEMPTS_PER_PATH == 1
        assert m.MAX_REQUEST_COUNT == 4


# ===========================================================================
# B1-TEST-002 -- credential-source contract and secret non-disclosure.
# ===========================================================================


class TestB1Test002CredentialContract:
    def test_only_the_two_path_based_names_accepted(self):
        refs = m.load_b1_credentials(make_env())
        assert refs.api_key_id == CURRENT_KEY_ID
        assert refs.private_key_path == PRIVATE_KEY_PATH_VALUE

    def test_missing_reference_rejected(self):
        with pytest.raises(m.CredentialSourceContractError):
            m.load_b1_credentials({m.PRIVATE_KEY_PATH_ENV: PRIVATE_KEY_PATH_VALUE})
        with pytest.raises(m.CredentialSourceContractError):
            m.load_b1_credentials({m.API_KEY_ID_ENV: CURRENT_KEY_ID})

    def test_pem_content_in_path_variable_rejected(self):
        pem_ish = "-----BEGIN PRIVATE KEY-----\nMIIB...\n-----END PRIVATE KEY-----\n"
        with pytest.raises(m.CredentialSourceContractError):
            m.load_b1_credentials(make_env(**{m.PRIVATE_KEY_PATH_ENV: pem_ish}))

    def test_older_pem_variable_not_silently_substituted(self):
        env = make_env(**{m.FORBIDDEN_PRIVATE_KEY_PEM_ENV: "-----BEGIN PRIVATE KEY-----"})
        with pytest.raises(m.CredentialSourceContractError):
            m.load_b1_credentials(env)
        # And via the execute boundary: terminal capability/scope violation.
        result, _ = run_probe(full_discovery_script(), env=env)
        assert result.terminal_outcome == m.B1TerminalOutcome.B1_CAPABILITY_OR_SCOPE_VIOLATION
        assert result.manifest.request_count == 0

    def test_secret_values_never_appear_in_repr(self):
        refs = m.load_b1_credentials(make_env())
        assert CURRENT_KEY_ID not in repr(refs)
        assert PRIVATE_KEY_PATH_VALUE not in repr(refs)

        plan = m.build_request_plan_sequence()[0]
        sm = m.build_signing_message(plan, "1724800000000")
        signature_b64 = base64.b64encode(b"\xaa" * 48).decode("ascii")
        request = m.build_authenticated_request(plan, sm, signature_b64, CURRENT_KEY_ID)
        text = repr(request)
        assert signature_b64 not in text
        assert CURRENT_KEY_ID not in text
        assert "1724800000000" not in text
        assert "redacted" in text

    def test_full_run_evidence_excludes_secrets(self, tmp_path):
        result, _ = run_probe(full_discovery_script(), output_root=str(tmp_path))
        summary_bytes = result.summary.to_json_bytes()
        manifest_bytes = result.manifest.to_json_bytes()
        for blob in (summary_bytes, manifest_bytes, repr(result).encode()):
            for secret in (
                CURRENT_KEY_ID.encode(),
                UNRELATED_KEY_ID.encode(),
                UNRELATED_KEY_NAME.encode(),
                PRIVATE_KEY_PATH_VALUE.encode(),
                b"BEGIN PRIVATE KEY",
                b"KALSHI-ACCESS",
            ):
                assert secret not in blob

    def test_matching_keeps_unrelated_key_identifiers_out_of_summary(self):
        result, _ = run_probe(full_discovery_script())
        summary = json.loads(result.summary.to_json_bytes())
        assert summary["current_key"]["match_state"] == "UNIQUE"
        assert UNRELATED_KEY_ID not in json.dumps(summary)
        assert UNRELATED_KEY_NAME not in json.dumps(summary)

    def test_api_key_record_repr_redacts_identifiers(self):
        record = m.ApiKeyRecord(
            api_key_id="SECRET-ID", name="secret-name", scopes=("read",), subaccount=3
        )
        text = repr(record)
        assert "SECRET-ID" not in text and "secret-name" not in text
        assert "redacted" in text


# ===========================================================================
# B1-TEST-003 -- request deadline / budget.
# ===========================================================================


class TestB1Test003Deadlines:
    def test_per_request_deadline_includes_read_and_parse(self):
        clock = FakeClock()
        script = {m.OP_ACCOUNT_LIMITS: resp(account_limits_body(), pre_ms=10_001)}
        result, transport = run_probe(script, clock=clock)
        assert result.terminal_outcome == m.B1TerminalOutcome.B1_READ_FAILURE
        assert result.detail == "TIMEOUT"
        assert result.manifest.request_count == 1
        assert len(transport.calls) == 1  # no resend

    def test_within_per_request_deadline_proceeds(self):
        clock = FakeClock()
        script = full_discovery_script()
        # 9s elapsed inside request 1 only; still under the 10s per-request cap
        # and the 40s global cap.
        script[m.OP_ACCOUNT_LIMITS] = resp(account_limits_body(), pre_ms=9_000)
        result, _ = run_probe(script, clock=clock)
        assert result.terminal_outcome == (
            m.B1TerminalOutcome.B1_EXISTING_NUMBERED_SUBACCOUNT_DISCOVERED
        )

    def test_global_deadline_anchored_once_and_never_reset(self, monkeypatch):
        seen: list[int] = []
        real = m._perform_one_request

        def spy(**kwargs):
            seen.append(kwargs["global_deadline_ns"])
            return real(**kwargs)

        monkeypatch.setattr(m, "_perform_one_request", spy)
        run_probe(full_discovery_script())
        assert len(seen) == 4
        # One immutable global deadline shared by every request; never reset.
        assert len(set(seen)) == 1

    def test_global_deadline_exhaustion_halts(self):
        clock = FakeClock()
        script = {m.OP_ACCOUNT_LIMITS: resp(account_limits_body(), pre_ms=40_001)}
        result, transport = run_probe(script, clock=clock)
        assert result.terminal_outcome == m.B1TerminalOutcome.B1_READ_FAILURE
        assert result.detail == "TIMEOUT"
        assert len(transport.calls) == 1  # no resend

    def test_timeout_outcome_from_transport_has_no_resend(self):
        clock = FakeClock()
        script = {m.OP_ACCOUNT_LIMITS: Scripted(kind="TIMEOUT")}
        result, transport = run_probe(script, clock=clock)
        assert result.terminal_outcome == m.B1TerminalOutcome.B1_READ_FAILURE
        assert len(transport.calls) == 1
        assert result.manifest.requests[0].status_class == m.RequestStatusClass.TIMEOUT

    def test_retry_and_redirect_counters_are_zero(self):
        result, _ = run_probe(full_discovery_script())
        summary = json.loads(result.summary.to_json_bytes())
        manifest = json.loads(result.manifest.to_json_bytes())
        assert summary["retry_count"] == 0 == manifest["retry_count"]
        assert summary["redirect_count"] == 0 == manifest["redirect_count"]
        assert m.AUTOMATIC_RETRY_COUNT == 0 and m.MAX_REDIRECT_COUNT == 0


# ===========================================================================
# B1-TEST-004 -- response size limits (now enforced at the read boundary).
# ===========================================================================


class TestB1Test004SizeLimits:
    def test_per_response_byte_boundary_accepted_and_exceeded(self):
        # Exactly 262144 bytes -> the B1-owned loop returns them (a clean EOF
        # via the bounded sentinel read).
        data, reader, _ = drive_read(
            b"x" * m.MAX_RESPONSE_BYTES_PER_REQUEST, read_size=40_000
        )
        assert len(data) == m.MAX_RESPONSE_BYTES_PER_REQUEST
        assert reader.closed is False  # the runner, not this helper, closes it

        # 262145 bytes -> RESPONSE_TOO_LARGE at the read boundary.
        with pytest.raises(m._ResponseTooLarge):
            drive_read(
                b"x" * (m.MAX_RESPONSE_BYTES_PER_REQUEST + 1), read_size=40_000
            )

    def test_byte_262145_halts_even_when_split_across_reads(self):
        with pytest.raises(m._ResponseTooLarge):
            drive_read(
                b"x" * (m.MAX_RESPONSE_BYTES_PER_REQUEST + 1), read_size=64
            )

    def test_cumulative_total_cap_enforced_in_b1_loop(self):
        prior = m.MAX_TOTAL_RESPONSE_BYTES - m.MAX_RESPONSE_BYTES_PER_REQUEST
        data, _, _ = drive_read(
            b"x" * m.MAX_RESPONSE_BYTES_PER_REQUEST, total_prior=prior
        )
        assert len(data) == m.MAX_RESPONSE_BYTES_PER_REQUEST

        with pytest.raises(m._ResponseTooLarge):
            drive_read(
                b"x" * m.MAX_RESPONSE_BYTES_PER_REQUEST, total_prior=prior + 1
            )

    def test_integration_262145_bytes_halts(self):
        oversized = b'{"api_keys":[]}' + b" " * (
            m.MAX_RESPONSE_BYTES_PER_REQUEST + 1 - len(b'{"api_keys":[]}')
        )
        script = {
            m.OP_ACCOUNT_LIMITS: resp(account_limits_body()),
            m.OP_API_KEYS: resp(None, raw_body=oversized),
        }
        result, _ = run_probe(script)
        assert result.terminal_outcome == (
            m.B1TerminalOutcome.B1_AUTHORITATIVE_RESPONSE_MALFORMED
        )
        assert result.manifest.requests[-1].status_class == (
            m.RequestStatusClass.RESPONSE_TOO_LARGE
        )

    def test_integration_262144_bytes_not_rejected_for_size(self):
        exact = b'{"api_keys":[]}' + b" " * (
            m.MAX_RESPONSE_BYTES_PER_REQUEST - len(b'{"api_keys":[]}')
        )
        assert len(exact) == m.MAX_RESPONSE_BYTES_PER_REQUEST
        script = {
            m.OP_ACCOUNT_LIMITS: resp(account_limits_body()),
            m.OP_API_KEYS: resp(None, raw_body=exact),
        }
        result, _ = run_probe(script)
        # Zero matches -> a key-matching terminal, never a size terminal.
        assert result.terminal_outcome == (
            m.B1TerminalOutcome.B1_CURRENT_KEY_NOT_UNIQUELY_MATCHED
        )


# ===========================================================================
# B1-TEST-005 -- account limits schema.
# ===========================================================================


class TestB1Test005AccountLimits:
    def test_all_recognized_tiers_accepted(self):
        for tier in m.RECOGNIZED_USAGE_TIERS:
            projection = m.parse_account_limits(account_limits_body(tier))
            assert projection.usage_tier == tier
            assert len(projection.relevant_grants) == 1  # only event_contract

    def test_unrecognized_tier_is_source_drift(self):
        with pytest.raises(m.B1ProbeError):
            m.parse_account_limits(account_limits_body("titanium"))
        script = {m.OP_ACCOUNT_LIMITS: resp(account_limits_body("titanium"))}
        result, _ = run_probe(script)
        assert result.terminal_outcome == m.B1TerminalOutcome.B1_SOURCE_DRIFT

    def test_bool_is_not_accepted_as_int(self):
        body = account_limits_body()
        body["read"]["refill_rate"] = True
        with pytest.raises(m.B1ProbeError):
            m.parse_account_limits(body)

    def test_missing_projection_field_rejected(self):
        body = account_limits_body()
        del body["grants"]
        with pytest.raises(m.B1ProbeError):
            m.parse_account_limits(body)

    def test_malformed_grant_rejected(self):
        body = account_limits_body()
        body["grants"] = [{"level": "x", "source": "y"}]  # no exchange_instance
        with pytest.raises(m.B1ProbeError):
            m.parse_account_limits(body)

    def test_rate_metadata_values_not_persisted(self):
        result, _ = run_probe(full_discovery_script())
        blob = result.summary.to_json_bytes()
        assert b"refill_rate" not in blob
        assert b"bucket_capacity" not in blob


# ===========================================================================
# B1-TEST-006 -- API-key matching / restriction.
# ===========================================================================


class TestB1Test006ApiKeyMatching:
    def test_exactly_one_match_required(self):
        result, _ = run_probe(full_discovery_script())
        summary = json.loads(result.summary.to_json_bytes())
        assert summary["current_key"]["match_state"] == "UNIQUE"

    def test_zero_matches_halts(self):
        body = {"api_keys": [{"api_key_id": "other", "name": "n", "scopes": ["read"]}]}
        script = {
            m.OP_ACCOUNT_LIMITS: resp(account_limits_body()),
            m.OP_API_KEYS: resp(body),
        }
        result, _ = run_probe(script)
        assert result.terminal_outcome == (
            m.B1TerminalOutcome.B1_CURRENT_KEY_NOT_UNIQUELY_MATCHED
        )
        assert json.loads(result.summary.to_json_bytes())["current_key"][
            "match_state"
        ] == "ZERO_MATCH"

    def test_multiple_matches_halts(self):
        body = {
            "api_keys": [
                {"api_key_id": CURRENT_KEY_ID, "name": "a", "scopes": ["read"]},
                {"api_key_id": CURRENT_KEY_ID, "name": "b", "scopes": ["read"]},
            ]
        }
        script = {
            m.OP_ACCOUNT_LIMITS: resp(account_limits_body()),
            m.OP_API_KEYS: resp(body),
        }
        result, _ = run_probe(script)
        assert result.terminal_outcome == (
            m.B1TerminalOutcome.B1_CURRENT_KEY_NOT_UNIQUELY_MATCHED
        )
        assert json.loads(result.summary.to_json_bytes())["current_key"][
            "match_state"
        ] == "MULTIPLE_MATCHES"

    def test_absent_or_null_is_not_exposed_without_source_definition(self):
        for kwargs in ({"subaccount": m._ABSENT}, {"include_subaccount_null": True}):
            script = {
                m.OP_ACCOUNT_LIMITS: resp(account_limits_body()),
                m.OP_API_KEYS: resp(api_keys_body(**kwargs)),
            }
            result, transport = run_probe(script, source=not_exposed_source())
            assert result.terminal_outcome == (
                m.B1TerminalOutcome
                .B1_ACCOUNT_WIDE_ENUMERATION_NOT_PROVEN_WITH_CURRENT_KEY
            )
            summary = json.loads(result.summary.to_json_bytes())
            assert summary["current_key"]["restriction_state"] == "NOT_EXPOSED"
            assert summary["enumeration"]["account_wide_enumeration_proven"] is False
            assert len(transport.calls) == 2  # balances/netting not attempted

    def test_absent_or_null_is_unrestricted_only_under_source_fixture(self):
        result, _ = run_probe(
            full_discovery_script(api_keys=api_keys_body(include_subaccount_null=True)),
            source=unrestricted_source(),
        )
        summary = json.loads(result.summary.to_json_bytes())
        assert summary["current_key"]["restriction_state"] == "UNRESTRICTED"
        assert summary["enumeration"]["account_wide_enumeration_proven"] is True

    def test_integer_boundaries_accepted_as_exact_restriction(self):
        for n in (0, 63):
            script = {
                m.OP_ACCOUNT_LIMITS: resp(account_limits_body()),
                m.OP_API_KEYS: resp(api_keys_body(subaccount=n)),
            }
            result, transport = run_probe(script, source=unrestricted_source())
            assert result.terminal_outcome == (
                m.B1TerminalOutcome
                .B1_ACCOUNT_WIDE_ENUMERATION_NOT_PROVEN_WITH_CURRENT_KEY
            )
            summary = json.loads(result.summary.to_json_bytes())
            assert summary["current_key"]["restriction_state"] == (
                "RESTRICTED_TO_EXACT_SUBACCOUNT"
            )
            assert summary["current_key"]["restricted_subaccount_number"] == n
            assert len(transport.calls) == 2

    def test_out_of_range_bool_and_string_subaccount_rejected(self):
        for bad in (-1, 64, True, "1"):
            script = {
                m.OP_ACCOUNT_LIMITS: resp(account_limits_body()),
                m.OP_API_KEYS: resp(api_keys_body(subaccount=bad)),
            }
            result, _ = run_probe(script)
            assert result.terminal_outcome == (
                m.B1TerminalOutcome.B1_AUTHORITATIVE_RESPONSE_MALFORMED
            )

    def test_exact_restricted_key_403_vs_generic_403(self):
        sig = not_exposed_source().restricted_key_error_signature
        exact_body = {sig.field_name: sig.expected_value, "message": "restricted"}
        script = {
            m.OP_ACCOUNT_LIMITS: resp(account_limits_body()),
            m.OP_API_KEYS: resp(exact_body, status=403),
        }
        result, transport = run_probe(script)
        assert result.terminal_outcome == (
            m.B1TerminalOutcome.B1_ACCOUNT_WIDE_ENUMERATION_NOT_PROVEN_WITH_CURRENT_KEY
        )
        assert json.loads(result.summary.to_json_bytes())["current_key"][
            "restriction_state"
        ] == "RESTRICTED_EXACT_SUBACCOUNT_NOT_PROVEN"
        assert len(transport.calls) == 2  # balances/netting not attempted

        script[m.OP_API_KEYS] = resp({"code": "unrelated"}, status=403)
        result2, _ = run_probe(script)
        assert result2.terminal_outcome == (
            m.B1TerminalOutcome.B1_READ_CAPABILITY_INSUFFICIENT
        )


# ===========================================================================
# B1-TEST-007 -- balance fixed-point semantics.
# ===========================================================================


class TestB1Test007BalanceDecimal:
    @pytest.mark.parametrize("text", ["0", "0.0", "-0.000000", "0.000000", "-0"])
    def test_zero_forms(self, text):
        value, cls = m.parse_balance_decimal(text)
        assert cls == m.BalanceClass.ZERO

    @pytest.mark.parametrize("text", ["1", "0.01", "-1", "-0.000001", "123456.999999"])
    def test_nonzero_forms(self, text):
        value, cls = m.parse_balance_decimal(text)
        assert cls == m.BalanceClass.NONZERO

    @pytest.mark.parametrize(
        "text",
        ["1e5", "NaN", "Infinity", "+1", " 1", "1 ", "1,000", "0.1234567", "01", "", ".5", "1."],
    )
    def test_rejected_forms(self, text):
        with pytest.raises(m.B1ProbeError):
            m.parse_balance_decimal(text)

    def test_non_string_rejected(self):
        with pytest.raises(m.B1ProbeError):
            m.parse_balance_decimal(1)
        with pytest.raises(m.B1ProbeError):
            m.parse_balance_decimal(1.5)

    def test_exact_dollar_values_absent_from_summary(self):
        script = full_discovery_script()
        script[m.OP_SUBACCOUNT_BALANCES] = resp(
            balances_body([brow(0, balance="0"), brow(2, balance="12.345678")])
        )
        result, _ = run_probe(script)
        blob = result.summary.to_json_bytes()
        assert b"12.345678" not in blob
        summary = json.loads(blob)
        classes = {
            entry["subaccount_number"]: entry["class"]
            for entry in summary["enumeration"]["balance_classes"]
        }
        assert classes == {0: "ZERO", 2: "NONZERO"}

    def test_multi_exchange_index_aggregation(self):
        rows = [
            brow(0, idx=0, balance="0"),
            brow(0, idx=1, balance="0"),
            brow(2, idx=0, balance="0"),
            brow(2, idx=1, balance="0.01"),
        ]
        parsed = m.parse_subaccount_balances(balances_body(rows))
        summary = m._summarize_balance_classes(parsed)
        assert dict(summary) == {0: m.BalanceClass.ZERO, 2: m.BalanceClass.NONZERO}


# ===========================================================================
# B1-TEST-008 -- subaccount identity reconciliation.
# ===========================================================================


class TestB1Test008Reconciliation:
    def test_subaccount_number_boundaries(self):
        assert m._require_subaccount_number(0) == 0
        assert m._require_subaccount_number(63) == 63
        for bad in (-1, 64, True, "0"):
            with pytest.raises(m.B1ProbeError):
                m._require_subaccount_number(bad)

    def test_primary_zero_mandatory(self):
        script = full_discovery_script()
        script[m.OP_SUBACCOUNT_BALANCES] = resp(
            balances_body([brow(1), brow(2)])  # no subaccount 0
        )
        result, _ = run_probe(script)
        assert result.terminal_outcome == m.B1TerminalOutcome.B1_SOURCE_DRIFT

    def test_equal_sets_succeed(self):
        result, _ = run_probe(full_discovery_script(numbered=(1, 4)))
        summary = json.loads(result.summary.to_json_bytes())
        assert summary["enumeration"]["surfaces_agree"] is True
        assert summary["enumeration"]["balance_subaccount_numbers"] == [0, 1, 4]
        assert summary["enumeration"]["numbered_subaccounts"] == [1, 4]

    def test_differing_sets_halt_without_union_or_intersection(self):
        script = full_discovery_script()
        script[m.OP_SUBACCOUNT_BALANCES] = resp(balances_body([brow(0), brow(2)]))
        script[m.OP_SUBACCOUNT_NETTING] = resp(netting_body([nrow(0), nrow(3)]))
        result, _ = run_probe(script)
        assert result.terminal_outcome == (
            m.B1TerminalOutcome.B1_SUBACCOUNT_ENUMERATION_DISAGREEMENT
        )
        summary = json.loads(result.summary.to_json_bytes())
        assert summary["enumeration"]["balance_subaccount_numbers"] == [0, 2]
        assert summary["enumeration"]["netting_subaccount_numbers"] == [0, 3]
        assert summary["enumeration"]["numbered_subaccounts"] == []  # no inference
        assert summary["enumeration"]["account_wide_enumeration_proven"] is False

    def test_numeric_gaps_not_synthesized(self):
        result, _ = run_probe(full_discovery_script(numbered=(2,)))
        summary = json.loads(result.summary.to_json_bytes())
        assert summary["enumeration"]["balance_subaccount_numbers"] == [0, 2]
        assert summary["enumeration"]["numbered_subaccounts"] == [2]

    def test_exact_duplicate_rows_contribute_once(self):
        rows = [brow(0, balance="0"), brow(0, balance="0"), brow(2, balance="1.00")]
        parsed = m.parse_subaccount_balances(balances_body(rows))
        assert len(parsed) == 2

    def test_conflicting_duplicate_rows_halt(self):
        rows = [brow(0, balance="0"), brow(0, balance="5.00")]
        with pytest.raises(m.B1ProbeError):
            m.parse_subaccount_balances(balances_body(rows))
        nrows = [nrow(0, enabled=True), nrow(0, enabled=False)]
        with pytest.raises(m.B1ProbeError):
            m.parse_subaccount_netting(netting_body(nrows))


# ===========================================================================
# B1-TEST-009 -- terminal and next-route theorem.
# ===========================================================================


class TestB1Test009TerminalTheorem:
    def test_numbered_set_nonempty_is_discovered(self):
        result, _ = run_probe(full_discovery_script(numbered=(5,)))
        assert result.terminal_outcome == (
            m.B1TerminalOutcome.B1_EXISTING_NUMBERED_SUBACCOUNT_DISCOVERED
        )
        assert result.next_route_class == (
            m.B1NextRouteClass.EXISTING_NUMBERED_CANDIDATES_REQUIRE_LATER_PROOF
        )
        neg = json.loads(result.summary.to_json_bytes())["negative_theorems"]
        assert neg["existing_numbered_subaccount_clean_inception_proven"] is False
        assert neg["existing_numbered_subaccount_complete_history_proven"] is False

    def test_primary_only_observed(self):
        script = full_discovery_script(numbered=())
        result, _ = run_probe(script)
        assert result.terminal_outcome == m.B1TerminalOutcome.B1_PRIMARY_ONLY_OBSERVED
        assert result.next_route_class == (
            m.B1NextRouteClass.NO_NUMBERED_DOMAIN_CURRENTLY_OBSERVED
        )
        summary = json.loads(result.summary.to_json_bytes())
        assert summary["enumeration"]["balance_subaccount_numbers"] == [0]
        assert summary["enumeration"]["numbered_subaccounts"] == []

    def test_restricted_key_never_produces_account_wide_absence(self):
        script = {
            m.OP_ACCOUNT_LIMITS: resp(account_limits_body()),
            m.OP_API_KEYS: resp(api_keys_body(subaccount=9)),
        }
        result, _ = run_probe(script, source=unrestricted_source())
        summary = json.loads(result.summary.to_json_bytes())
        assert result.terminal_outcome != m.B1TerminalOutcome.B1_PRIMARY_ONLY_OBSERVED
        assert summary["enumeration"]["account_wide_enumeration_proven"] is False
        assert summary["enumeration"]["balance_subaccount_numbers"] == []

    def test_source_drift_precedes_success(self):
        script = full_discovery_script()
        script[m.OP_ACCOUNT_LIMITS] = resp(account_limits_body("titanium"))
        result, _ = run_probe(script)
        assert result.terminal_outcome == m.B1TerminalOutcome.B1_SOURCE_DRIFT

    def test_next_route_mapping_is_total(self):
        for outcome in m.B1TerminalOutcome:
            assert outcome in m._NEXT_ROUTE_BY_OUTCOME
            assert isinstance(
                m._NEXT_ROUTE_BY_OUTCOME[outcome], m.B1NextRouteClass
            )

    def test_terminal_precedence_covers_every_outcome(self):
        assert set(m.TERMINAL_PRECEDENCE) == set(m.B1TerminalOutcome)
        assert len(m.TERMINAL_PRECEDENCE) == len(m.B1TerminalOutcome)


# ===========================================================================
# B1-TEST-010 -- negative-theorem serialization.
# ===========================================================================

_REQUIRED_NEGATIVE_THEOREMS = {
    "historical_primary_incident_resolved",
    "historical_primary_writer_proof_released",
    "historical_primary_safe_to_reuse",
    "existing_numbered_subaccount_clean_inception_proven",
    "existing_numbered_subaccount_complete_history_proven",
    "existing_numbered_subaccount_zero_exposure_proven",
    "subaccount_creation_authorized",
    "funding_or_transfer_authorized",
    "canary_execution_ready",
    "market_maker_execution_ready",
    "production_behavior_known",
    "profitability_known",
    "arbitrage_proven",
}


class TestB1Test010NegativeTheorems:
    def _scenarios(self):
        return {
            "discovered": full_discovery_script(numbered=(2,)),
            "primary_only": full_discovery_script(numbered=()),
            "malformed": {
                m.OP_ACCOUNT_LIMITS: resp({"usage_tier": "advanced"})  # missing fields
            },
            "read_failure": {m.OP_ACCOUNT_LIMITS: Scripted(kind="TRANSPORT_ERROR")},
            "source_drift": {
                m.OP_ACCOUNT_LIMITS: resp(account_limits_body("titanium"))
            },
        }

    def test_every_scenario_serializes_all_negative_theorems_false(self):
        for name, script in self._scenarios().items():
            result, _ = run_probe(script)
            summary = json.loads(result.summary.to_json_bytes())
            neg = summary["negative_theorems"]
            assert set(neg) == _REQUIRED_NEGATIVE_THEOREMS, name
            assert all(value is False for value in neg.values()), name
            assert summary["historical_primary"] == {
                "writer_proof_state": "HELD",
                "unresolved_exposure": "UNKNOWN_UNBOUNDED",
                "normal_writer_eligible": False,
            }, name
            assert summary["create_subaccount"]["capability"] == (
                "NOT_PROVEN_BY_B1_READ_ONLY_FACTS"
            ), name


# ===========================================================================
# B1-TEST-011 -- source binding.
# ===========================================================================


class TestB1Test011SourceBinding:
    def test_source_binding_record_identity(self):
        raw = m.SOURCE_BINDING_RECORD_JSON.encode("utf-8")
        assert len(raw) == m.SOURCE_BINDING_RECORD_BYTES == 3307
        import hashlib

        assert hashlib.sha256(raw).hexdigest() == m.SOURCE_BINDING_RECORD_SHA256
        assert m.verify_source_binding_record(raw) is True
        assert m.verify_source_binding_record(raw + b" ") is False

    def test_record_marks_fresh_openapi_as_not_exposed(self):
        record = json.loads(m.SOURCE_BINDING_RECORD_JSON)
        assert record["fresh_operation_ids"] == "NOT_EXPOSED_BY_RENDERED_SOURCE"
        assert record["fresh_openapi_version"] == "NOT_EXPOSED_BY_RENDERED_SOURCE"
        assert record["fresh_raw_openapi_status"].startswith("NOT_OBTAINED")

    def test_historical_operation_ids_are_labelled_historical(self):
        assert set(m.HISTORICAL_CORROBORATING_OPERATION_IDS) == {
            "GET /account/limits",
            "GET /api_keys",
            "GET /portfolio/subaccounts/balances",
            "GET /portfolio/subaccounts/netting",
            "POST /portfolio/subaccounts",
        }
        result, _ = run_probe(full_discovery_script())
        blob = result.summary.to_json_bytes()
        for historical_id in m.HISTORICAL_CORROBORATING_OPERATION_IDS.values():
            assert historical_id.encode() not in blob

    def test_reviewed_method_path_projection(self):
        record = m.authoring_task_current_source_record()
        evaluation = record.evaluate_against_reviewed_contract()
        assert evaluation.status == m.SourceEvaluationStatus.OK
        for label in m.OPERATION_LABELS:
            op = record.operation(label)
            assert op.method == "GET"
            assert op.path == m.OP_BASE_PATHS[label]

    def test_material_drift_is_classified(self):
        base = m.authoring_task_current_source_record()
        drifted_ops = tuple(
            dataclasses.replace(op, path="/v3" + op.path) if op.label == m.OP_API_KEYS else op
            for op in base.operations
        )
        drifted = dataclasses.replace(base, operations=drifted_ops)
        assert drifted.evaluate_against_reviewed_contract().status == (
            m.SourceEvaluationStatus.DRIFT
        )
        result, _ = run_probe(full_discovery_script(), source=drifted)
        assert result.terminal_outcome == m.B1TerminalOutcome.B1_SOURCE_DRIFT
        assert result.manifest.request_count == 0

    def test_declared_conflict_is_official_source_conflict(self):
        conflicted = dataclasses.replace(
            m.authoring_task_current_source_record(), declares_unresolved_conflict=True
        )
        assert conflicted.evaluate_against_reviewed_contract().status == (
            m.SourceEvaluationStatus.CONFLICT
        )
        result, _ = run_probe(full_discovery_script(), source=conflicted)
        assert result.terminal_outcome == m.B1TerminalOutcome.B1_OFFICIAL_SOURCE_CONFLICT

    def test_drifted_subaccount_range_detected(self):
        drifted = dataclasses.replace(
            m.authoring_task_current_source_record(), subaccount_number_max=32
        )
        assert drifted.evaluate_against_reviewed_contract().status == (
            m.SourceEvaluationStatus.DRIFT
        )


# ===========================================================================
# B1-TEST-012 -- artifact sensitivity / evidence separation.
# ===========================================================================


class TestB1Test012ArtifactSensitivity:
    def test_raw_bodies_local_only_by_default(self):
        result, _ = run_probe(full_discovery_script())
        assert len(result.raw_responses) == 4
        assert all(isinstance(body, bytes) for _, body in result.raw_responses)

    def test_write_evidence_requires_explicit_root(self):
        result, _ = run_probe(full_discovery_script())
        with pytest.raises(ValueError):
            result.write_evidence("")

    def test_external_output_root_receives_exact_raw_bytes(self, tmp_path):
        script = full_discovery_script()
        result, _ = run_probe(script, output_root=str(tmp_path))
        summary_path = tmp_path / m.SANITIZED_SUMMARY_FILENAME
        manifest_path = tmp_path / m.EVIDENCE_MANIFEST_FILENAME
        assert summary_path.is_file() and manifest_path.is_file()

        for label in m.OPERATION_LABELS:
            raw_path = tmp_path / m.LOCAL_RAW_BODY_FILENAMES[label]
            assert raw_path.is_file()
            assert raw_path.read_bytes() == script[label].body

        for path in (summary_path, manifest_path):
            blob = path.read_bytes()
            for forbidden in (
                CURRENT_KEY_ID.encode(),
                UNRELATED_KEY_ID.encode(),
                UNRELATED_KEY_NAME.encode(),
                PRIVATE_KEY_PATH_VALUE.encode(),
                b"BEGIN PRIVATE KEY",
                b"KALSHI-ACCESS",
                b"1.25",  # exact dollar balance from the fixture
            ):
                assert forbidden not in blob

    def test_manifest_projection_shape(self, tmp_path):
        result, _ = run_probe(full_discovery_script(), output_root=str(tmp_path))
        manifest = json.loads(result.manifest.to_json_bytes())
        assert manifest["schema_revision"] == 1
        assert manifest["task_id"] == m.TASK_ID
        assert manifest["environment"] == "KALSHI_DEMO"
        assert manifest["demo_rest_base_url"] == m.DEMO_REST_BASE_URL
        assert manifest["source_binding_record_sha256"] == (
            unrestricted_source().binding_record_sha256
        )
        assert manifest["source_binding_record_sha256"] != m.SOURCE_BINDING_RECORD_SHA256
        assert manifest["retry_count"] == 0 and manifest["redirect_count"] == 0
        assert len(manifest["requests"]) == 4
        for i, entry in enumerate(manifest["requests"], start=1):
            assert entry["sequence"] == i
            assert entry["method"] == "GET"
            assert entry["path"] in m.OP_BASE_PATHS.values()
            assert entry["status_class"] == "OK_200"
            assert re.fullmatch(r"[0-9a-f]{64}", entry["raw_response_sha256"])
            assert entry["local_raw_body_filename"] in m.LOCAL_RAW_BODY_FILENAMES.values()
        flat = json.dumps(manifest)
        for banned in ("signature", "authorization", "KALSHI-ACCESS", "private_key"):
            assert banned.lower() not in flat.lower()

    def test_summary_evidence_manifest_hash_matches(self, tmp_path):
        result, _ = run_probe(full_discovery_script(), output_root=str(tmp_path))
        summary = json.loads(result.summary.to_json_bytes())
        import hashlib

        recomputed = hashlib.sha256(result.manifest.to_json_bytes()).hexdigest()
        assert summary["evidence_manifest"]["sha256"] == recomputed
        assert summary["evidence_manifest"]["raw_bytes"] == len(
            result.manifest.to_json_bytes()
        )


# ===========================================================================
# C01-01 -- global / per-request deadline lifecycle (Marco finding 1).
# ===========================================================================


class TestC0101DeadlineLifecycle:
    def test_global_deadline_anchored_before_any_other_boundary_work(self):
        clock = OrderRecordingClock()
        transport = ScriptedTransport(clock, full_discovery_script())
        m.execute_b1_account_subaccount_probe(
            credentials_env=make_env(),
            source_record=unrestricted_source(),
            transport=transport,
            signer=FakeSigner(),
            clock=clock,
        )
        # The very first clock read of the boundary is the monotonic anchor,
        # ahead of the wall-clock read that _RunState construction needs.
        assert clock.events[0] == "mono"
        assert "wall" in clock.events
        assert clock.events.index("mono") < clock.events.index("wall")

    def test_global_anchor_shared_and_never_reset_across_all_four(self, monkeypatch):
        seen: list[int] = []
        real = m._perform_one_request

        def spy(**kwargs):
            seen.append(kwargs["global_deadline_ns"])
            return real(**kwargs)

        monkeypatch.setattr(m, "_perform_one_request", spy)
        clock = FakeClock()
        run_probe(full_discovery_script(), clock=clock)
        assert len(seen) == 4 and len(set(seen)) == 1
        # Anchored at the first monotonic read (0) + 40 000 ms.
        assert seen[0] == m.GLOBAL_EXECUTION_DEADLINE_MS * 1_000_000

    def test_per_request_timer_starts_at_network_not_signing(self):
        # Signing consumes 11 s -- more than the 10 s per-request budget but
        # less than the 40 s global budget. If signing were charged to the
        # per-request timer, request 1 would time out. With the fix it does
        # not, so the run reaches the (zero-match) api_keys terminal.
        clock = FakeClock()
        signer = SlowSigner(clock, advance_ms=11_000)
        script = {
            m.OP_ACCOUNT_LIMITS: resp(account_limits_body()),
            m.OP_API_KEYS: resp(
                {"api_keys": [{"api_key_id": "other", "name": "n", "scopes": ["read"]}]}
            ),
        }
        result, transport = run_probe(script, clock=clock, signer=signer)
        assert result.terminal_outcome == (
            m.B1TerminalOutcome.B1_CURRENT_KEY_NOT_UNIQUELY_MATCHED
        )
        assert result.manifest.request_count == 2
        assert len(transport.calls) == 2

    def test_signing_still_bounded_by_global_deadline(self):
        # 21 s + 21 s of signing exhausts the 40 s global budget before the
        # second request's network activity.
        clock = FakeClock()
        signer = SlowSigner(clock, advance_ms=21_000)
        result, transport = run_probe(
            full_discovery_script(), clock=clock, signer=signer
        )
        assert result.terminal_outcome == m.B1TerminalOutcome.B1_READ_FAILURE
        assert result.detail == "TIMEOUT"
        assert result.manifest.request_count == 2
        assert len(transport.calls) == 1  # second request never sent, no resend

    def test_crossing_during_bounded_body_acquisition(self):
        clock = FakeClock()
        # Two 6 s reads: after the first the clock is at 6 s (< 10 s), after
        # the second it is at 12 s; the B1-owned read loop's pre-read deadline
        # check then raises _DeadlineExceeded before the third read.
        script = {
            m.OP_ACCOUNT_LIMITS: resp(
                account_limits_body(), chunk_size=64, per_chunk_ms=6_000
            )
        }
        result, transport = run_probe(script, clock=clock)
        assert result.terminal_outcome == m.B1TerminalOutcome.B1_READ_FAILURE
        assert result.detail == "TIMEOUT"
        assert result.manifest.request_count == 1
        assert len(transport.calls) == 1  # no resend

    def test_crossing_during_parse(self, monkeypatch):
        clock = FakeClock()
        real_apply = m._apply_schema
        state = {"bumped": False}

        def slow_apply(*a, **kw):
            if not state["bumped"]:
                state["bumped"] = True
                clock.advance_ms(10_001)
            return real_apply(*a, **kw)

        monkeypatch.setattr(m, "_apply_schema", slow_apply)
        result, transport = run_probe(full_discovery_script(), clock=clock)
        assert result.terminal_outcome == m.B1TerminalOutcome.B1_READ_FAILURE
        assert result.detail == "TIMEOUT"
        assert result.manifest.request_count == 1
        assert len(transport.calls) == 1

    def test_crossing_during_request_evidence_construction(self, monkeypatch):
        clock = FakeClock()
        real_evidence = m.RequestEvidence
        state = {"bumped": False}

        def slow_evidence(**kw):
            if not state["bumped"]:
                state["bumped"] = True
                clock.advance_ms(10_001)
            return real_evidence(**kw)

        monkeypatch.setattr(m, "RequestEvidence", slow_evidence)
        result, transport = run_probe(full_discovery_script(), clock=clock)
        assert result.terminal_outcome == m.B1TerminalOutcome.B1_READ_FAILURE
        assert result.detail == "TIMEOUT"
        assert result.manifest.request_count == 1
        assert len(transport.calls) == 1

    def test_crossing_during_final_summary_manifest_construction(self, monkeypatch):
        clock = FakeClock()
        real_to_bytes = m.B1EvidenceManifest.to_json_bytes
        state = {"bumped": False}

        def slow_to_bytes(self):
            if not state["bumped"]:
                state["bumped"] = True
                clock.advance_ms(40_001)
            return real_to_bytes(self)

        monkeypatch.setattr(m.B1EvidenceManifest, "to_json_bytes", slow_to_bytes)
        # Full discovery would otherwise be DISCOVERED; the global deadline
        # crossing during terminal construction forces READ_FAILURE/TIMEOUT.
        result, _ = run_probe(full_discovery_script(), clock=clock)
        assert result.terminal_outcome == m.B1TerminalOutcome.B1_READ_FAILURE
        assert result.detail == "TIMEOUT"

    def test_global_deadline_does_not_mask_higher_precedence_terminal(self):
        # A source-conflict terminal (precedence 2) is not downgraded to
        # READ_FAILURE even if the clock is already past the global deadline
        # by terminal-construction time.
        clock = FakeClock()
        clock.advance_ms(0)
        conflicted = dataclasses.replace(
            m.authoring_task_current_source_record(), declares_unresolved_conflict=True
        )
        # Move the clock past the global deadline before _finish runs by using
        # a slow manifest serializer.
        assert m._enforce_global_deadline(
            FakeClock(start_ns=10 ** 18),
            m.GLOBAL_EXECUTION_DEADLINE_MS * 1_000_000,
            m.B1TerminalOutcome.B1_OFFICIAL_SOURCE_CONFLICT,
            "x",
        ) == (m.B1TerminalOutcome.B1_OFFICIAL_SOURCE_CONFLICT, "x")
        # And a success terminal IS downgraded.
        assert m._enforce_global_deadline(
            FakeClock(start_ns=10 ** 18),
            m.GLOBAL_EXECUTION_DEADLINE_MS * 1_000_000,
            m.B1TerminalOutcome.B1_PRIMARY_ONLY_OBSERVED,
            "",
        ) == (m.B1TerminalOutcome.B1_READ_FAILURE, "TIMEOUT")

    def test_post_send_transport_failure_never_resends(self):
        clock = FakeClock()
        script = {m.OP_ACCOUNT_LIMITS: Scripted(kind="TRANSPORT_ERROR")}
        result, transport = run_probe(script, clock=clock)
        assert result.terminal_outcome == m.B1TerminalOutcome.B1_READ_FAILURE
        assert result.detail == "TRANSPORT_FAILURE"
        assert result.manifest.request_count == 1
        assert len(transport.calls) == 1


# ===========================================================================
# C02-01 -- the immutable global deadline dominates through the terminal
# return, and no evidence is persisted by the execute boundary.
# ===========================================================================


def _success_state():
    """A minimal _RunState that looks like a completed four-request run."""

    state = m._RunState(started_at_utc="2026-08-27T20:10:00Z")
    state.request_count = 4
    state.usage_tier = "advanced"
    state.current_key_match_state = m.CurrentKeyMatchState.UNIQUE
    state.current_key_restriction_state = m.CurrentKeyRestrictionState.UNRESTRICTED
    state.balance_set = (0, 2)
    state.netting_set = (0, 2)
    state.surfaces_agree = True
    state.account_wide_enumeration_proven = True
    state.numbered_subaccounts = (2,)
    return state


class TestC0201TerminalReturnDeadlineDominance:
    def test_success_at_the_final_permitted_boundary_returns_the_success(self):
        # One tick before the global deadline: the success terminal survives.
        clock = FakeClock(start_ns=(m.GLOBAL_EXECUTION_DEADLINE_MS - 1) * 1_000_000)
        result = m._finish(
            _success_state(),
            m.B1TerminalOutcome.B1_PRIMARY_ONLY_OBSERVED,
            clock,
            m.GLOBAL_EXECUTION_DEADLINE_MS * 1_000_000,
            source_binding=authoring_emitted_identity(),
        )
        assert result.terminal_outcome == m.B1TerminalOutcome.B1_PRIMARY_ONLY_OBSERVED

    def test_one_tick_beyond_the_boundary_yields_timeout(self):
        clock = FakeClock(start_ns=m.GLOBAL_EXECUTION_DEADLINE_MS * 1_000_000)
        result = m._finish(
            _success_state(),
            m.B1TerminalOutcome.B1_PRIMARY_ONLY_OBSERVED,
            clock,
            m.GLOBAL_EXECUTION_DEADLINE_MS * 1_000_000,
            source_binding=authoring_emitted_identity(),
        )
        assert result.terminal_outcome == m.B1TerminalOutcome.B1_READ_FAILURE
        assert result.detail == "TIMEOUT"
        assert result.next_route_class == (
            m.B1NextRouteClass.RESOLVE_READ_SCOPE_OR_CREDENTIAL_LIMITATION
        )

    def test_deadline_crossing_during_late_summary_construction_yields_timeout(
        self, monkeypatch
    ):
        # The crossing happens INSIDE B1SanitizedSummary construction -- after
        # the manifest step -- which the prior correction did not gate.
        clock = FakeClock()
        real = m._summarize_balance_classes
        bumped = {"done": False}

        def slow(rows):
            if not bumped["done"]:
                bumped["done"] = True
                clock.advance_ms(m.GLOBAL_EXECUTION_DEADLINE_MS + 1)
            return real(rows)

        monkeypatch.setattr(m, "_summarize_balance_classes", slow)
        result, _ = run_probe(full_discovery_script(), clock=clock)
        assert result.terminal_outcome == m.B1TerminalOutcome.B1_READ_FAILURE
        assert result.detail == "TIMEOUT"
        # The returned manifest/summary are consistent with the timeout.
        summary = json.loads(result.summary.to_json_bytes())
        manifest = json.loads(result.manifest.to_json_bytes())
        assert summary["terminal_outcome"] == "B1_READ_FAILURE"
        assert summary["next_route_class"] == (
            "RESOLVE_READ_SCOPE_OR_CREDENTIAL_LIMITATION"
        )
        assert summary["request_count"] == manifest["request_count"] == 4
        assert summary["retry_count"] == 0 and summary["redirect_count"] == 0

    def test_deadline_crossing_during_result_projection_after_success_yields_timeout(
        self, monkeypatch
    ):
        clock = FakeClock()
        real = m.B1EvidenceManifest.to_json_bytes
        bumped = {"done": False}

        def slow(self):
            if not bumped["done"]:
                bumped["done"] = True
                clock.advance_ms(m.GLOBAL_EXECUTION_DEADLINE_MS + 1)
            return real(self)

        monkeypatch.setattr(m.B1EvidenceManifest, "to_json_bytes", slow)
        result, _ = run_probe(full_discovery_script(numbered=(2, 5)), clock=clock)
        assert result.terminal_outcome == m.B1TerminalOutcome.B1_READ_FAILURE
        assert result.detail == "TIMEOUT"

    def test_no_late_success_artifact_and_no_persistence_in_execute(
        self, monkeypatch, tmp_path
    ):
        clock = FakeClock()
        real = m._summarize_balance_classes
        bumped = {"done": False}

        def slow(rows):
            if not bumped["done"]:
                bumped["done"] = True
                clock.advance_ms(m.GLOBAL_EXECUTION_DEADLINE_MS + 1)
            return real(rows)

        monkeypatch.setattr(m, "_summarize_balance_classes", slow)
        # No output_root is threaded through execute at all: it cannot persist.
        result, _ = run_probe(full_discovery_script(), clock=clock)
        assert result.terminal_outcome == m.B1TerminalOutcome.B1_READ_FAILURE
        # Nothing was written anywhere by the execute boundary.
        assert list(tmp_path.iterdir()) == []
        # The in-memory terminal carries no success labelling.
        blob = result.summary.to_json_bytes()
        assert b'"terminal_outcome":"B1_READ_FAILURE"' in blob
        assert b"B1_PRIMARY_ONLY_OBSERVED" not in blob
        assert b"B1_EXISTING_NUMBERED_SUBACCOUNT_DISCOVERED" not in blob

    def test_timeout_reprojection_does_not_loop(self, monkeypatch):
        # _summarize_balance_classes is invoked once per _project_terminal
        # call; a single re-projection means exactly two invocations, never an
        # unbounded reclassification loop.
        clock = FakeClock()
        calls = {"n": 0}
        real = m._summarize_balance_classes

        def counting(rows):
            calls["n"] += 1
            if calls["n"] == 1:
                clock.advance_ms(m.GLOBAL_EXECUTION_DEADLINE_MS + 1)
            return real(rows)

        monkeypatch.setattr(m, "_summarize_balance_classes", counting)
        result, _ = run_probe(full_discovery_script(), clock=clock)
        assert result.terminal_outcome == m.B1TerminalOutcome.B1_READ_FAILURE
        assert calls["n"] == 2  # original projection + one timeout re-projection

    def test_global_start_deadline_never_reset_between_perform_and_finish(
        self, monkeypatch
    ):
        seen: list[tuple[str, int]] = []
        real_perform = m._perform_one_request
        real_finish = m._finish

        def perform_spy(**kw):
            seen.append(("perform", kw["global_deadline_ns"]))
            return real_perform(**kw)

        def finish_spy(
            state, outcome, clock, global_deadline_ns, source_binding=None, detail=""
        ):
            seen.append(("finish", global_deadline_ns))
            return real_finish(
                state,
                outcome,
                clock,
                global_deadline_ns,
                source_binding=source_binding,
                detail=detail,
            )

        monkeypatch.setattr(m, "_perform_one_request", perform_spy)
        monkeypatch.setattr(m, "_finish", finish_spy)
        run_probe(full_discovery_script())
        values = {v for _, v in seen}
        assert len(values) == 1  # one immutable global deadline, never reset
        assert ("finish", next(iter(values))) in seen


# ===========================================================================
# C02-02 -- the B1 runner (not the transport) owns the blocking
# response-body read loop.
# ===========================================================================


class _OverReader:
    """A reader that returns MORE bytes than requested -- a contract
    violation B1 must fail closed on."""

    def __init__(self) -> None:
        self.closed = False

    def read(self, max_bytes, timeout_ms):
        return b"x" * (max_bytes + 1)

    def close(self, timeout_ms):
        assert isinstance(timeout_ms, int) and timeout_ms > 0, timeout_ms
        self.closed = True


class _NonBytesReader:
    def __init__(self) -> None:
        self.closed = False

    def read(self, max_bytes, timeout_ms):
        return "not-bytes"

    def close(self, timeout_ms):
        assert isinstance(timeout_ms, int) and timeout_ms > 0, timeout_ms
        self.closed = True


class _FixedReaderTransport:
    """Establishes 200 + JSON headers and hands B1 a caller-supplied reader."""

    def __init__(self, reader) -> None:
        self._reader = reader
        self.calls = 0
        self.perform_timeouts: list[int] = []

    def perform(self, request, timeout_ms):
        assert isinstance(timeout_ms, int) and 0 < timeout_ms <= m.PER_REQUEST_DEADLINE_MS
        self.calls += 1
        self.perform_timeouts.append(timeout_ms)
        return m.TransportResponse(
            kind="RESPONSE",
            status=200,
            headers=(("Content-Type", "application/json"),),
            reader=self._reader,
        )


class TestC0102TransportBoundary:
    def test_transport_response_carries_no_body(self):
        names = {f.name for f in dataclasses.fields(m.TransportResponse)}
        assert names == {"kind", "status", "headers", "reader", "error_detail"}
        tr = m.TransportResponse(kind="RESPONSE", status=200)
        for banned in ("body", "body_bytes", "body_chunks", "chunks", "content"):
            assert not hasattr(tr, banned)

    def test_transport_perform_is_deadline_bound_and_rejects_sink(self):
        # C03-01-A: perform structurally receives a timeout/deadline budget
        # (and still no body sink). The Marco Correction 02 BLOCK finding was
        # exactly that this parameter was absent.
        params = list(inspect.signature(m.Transport.perform).parameters)
        assert params == ["self", "request", "timeout_ms"]
        assert "sink" not in params
        annotation = inspect.signature(m.Transport.perform).parameters[
            "timeout_ms"
        ].annotation
        assert annotation in (int, "int")
        with pytest.raises(m.CapabilityScopeViolation):
            m.UnavailableTransport().perform(object(), 10_000)

    def test_reader_protocol_shape(self):
        params = list(inspect.signature(m.ResponseBodyReader.read).parameters)
        assert params == ["self", "max_bytes", "timeout_ms"]
        # C03-01-C: close is deadline-bound too.
        close_params = list(inspect.signature(m.ResponseBodyReader.close).parameters)
        assert close_params == ["self", "timeout_ms"]

    def test_no_sink_type_or_read_all_path_remains(self):
        assert not hasattr(m, "BoundedResponseSink")
        assert "BoundedResponseSink" not in m.__all__
        src = Path(m.__file__).read_text(encoding="utf-8")
        # No whole-body convenience or transport-fed private sink loop: the
        # only body-read call site is the B1-owned ``reader.read(...)`` loop.
        assert "read_all(" not in src and "def read_all" not in src
        assert ".read_all" not in src
        assert "body_chunks" not in src
        assert "def feed(" not in src
        assert "_read_response_body" in src  # the B1-owned loop exists

    def test_b1_runner_owns_each_body_read_with_finite_positive_bounds(self):
        clock = FakeClock()
        # read_size forces the B1-owned loop to issue several bounded reads.
        script = full_discovery_script()
        script[m.OP_ACCOUNT_LIMITS] = resp(account_limits_body(), chunk_size=17)
        result, transport = run_probe(script, clock=clock)
        reader = transport.readers[m.OP_ACCOUNT_LIMITS]
        assert len(reader.calls) >= 2  # B1 issued the reads, one bounded at a time
        for max_bytes, timeout_ms in reader.calls:
            assert 0 < max_bytes <= m.RESPONSE_READ_CHUNK_BYTES
            assert 0 < timeout_ms <= m.PER_REQUEST_DEADLINE_MS
        assert reader.closed is True  # the runner closes the reader

    def test_deadline_checked_and_recomputed_before_the_first_read(self):
        clock = FakeClock()
        # 3 s elapse before the reader is handed back; the first B1-owned read
        # must therefore carry a recomputed budget of 7 s, not the full 10 s.
        script = full_discovery_script()
        script[m.OP_ACCOUNT_LIMITS] = resp(
            account_limits_body(), pre_ms=3_000, chunk_size=10 ** 9
        )
        result, transport = run_probe(script, clock=clock)
        reader = transport.readers[m.OP_ACCOUNT_LIMITS]
        assert reader.calls[0][1] == 7_000

    def test_deadline_recomputed_before_every_subsequent_read(self):
        clock = FakeClock()
        script = {
            m.OP_ACCOUNT_LIMITS: resp(account_limits_body()),
            m.OP_API_KEYS: resp(
                None, raw_body=b'{"api_keys":[]}', chunk_size=4, per_chunk_ms=500
            ),
        }
        result, transport = run_probe(script, clock=clock)
        reader = transport.readers[m.OP_API_KEYS]
        timeouts = [t for _, t in reader.calls]
        assert len(timeouts) >= 3
        assert timeouts == sorted(timeouts, reverse=True)  # strictly recomputed
        assert len(set(timeouts)) > 1

    def test_deadline_crossing_between_reads_prevents_the_next_read(self):
        clock = FakeClock()
        script = {
            m.OP_ACCOUNT_LIMITS: resp(
                account_limits_body(), chunk_size=8, per_chunk_ms=6_000
            )
        }
        result, transport = run_probe(script, clock=clock)
        assert result.terminal_outcome == m.B1TerminalOutcome.B1_READ_FAILURE
        assert result.detail == "TIMEOUT"
        reader = transport.readers[m.OP_ACCOUNT_LIMITS]
        assert len(reader.calls) == 2  # read1 -> 6s, read2 -> 12s, 3rd blocked
        assert len(transport.calls) == 1  # no resend

    def test_exact_262144_accepted_262145_is_response_too_large_via_runner(self):
        exact = b'{"api_keys":[]}' + b" " * (
            m.MAX_RESPONSE_BYTES_PER_REQUEST - len(b'{"api_keys":[]}')
        )
        over = exact + b" "
        r1, _ = run_probe(
            {
                m.OP_ACCOUNT_LIMITS: resp(account_limits_body()),
                m.OP_API_KEYS: resp(None, raw_body=exact, chunk_size=4096),
            }
        )
        assert r1.terminal_outcome == (
            m.B1TerminalOutcome.B1_CURRENT_KEY_NOT_UNIQUELY_MATCHED
        )
        r2, _ = run_probe(
            {
                m.OP_ACCOUNT_LIMITS: resp(account_limits_body()),
                m.OP_API_KEYS: resp(None, raw_body=over, chunk_size=4096),
            }
        )
        assert r2.terminal_outcome == (
            m.B1TerminalOutcome.B1_AUTHORITATIVE_RESPONSE_MALFORMED
        )
        assert r2.manifest.requests[-1].status_class == (
            m.RequestStatusClass.RESPONSE_TOO_LARGE
        )

    def test_reader_returning_more_than_requested_fails_closed(self):
        reader = _OverReader()
        transport = _FixedReaderTransport(reader)
        result = m.execute_b1_account_subaccount_probe(
            credentials_env=make_env(),
            source_record=unrestricted_source(),
            transport=transport,
            signer=FakeSigner(),
            clock=FakeClock(),
        )
        assert result.terminal_outcome == m.B1TerminalOutcome.B1_READ_FAILURE
        assert result.detail == "READ_CONTRACT_VIOLATION"
        assert result.manifest.request_count == 1
        assert reader.closed is True

    def test_reader_returning_non_bytes_fails_closed(self):
        transport = _FixedReaderTransport(_NonBytesReader())
        result = m.execute_b1_account_subaccount_probe(
            credentials_env=make_env(),
            source_record=unrestricted_source(),
            transport=transport,
            signer=FakeSigner(),
            clock=FakeClock(),
        )
        assert result.terminal_outcome == m.B1TerminalOutcome.B1_READ_FAILURE
        assert result.detail == "READ_CONTRACT_VIOLATION"

    def test_post_body_read_deadline_failure_invokes_zero_resend(self):
        clock = FakeClock()
        script = {
            m.OP_ACCOUNT_LIMITS: resp(
                account_limits_body(), chunk_size=8, per_chunk_ms=11_000
            )
        }
        result, transport = run_probe(script, clock=clock)
        assert result.terminal_outcome == m.B1TerminalOutcome.B1_READ_FAILURE
        assert result.detail == "TIMEOUT"
        assert len(transport.calls) == 1
        assert result.manifest.request_count == 1

    def test_cumulative_ceiling_enforced_across_the_b1_loop(self):
        assert (
            m.MAX_REQUEST_COUNT * m.MAX_RESPONSE_BYTES_PER_REQUEST
            == m.MAX_TOTAL_RESPONSE_BYTES
        )
        prior = m.MAX_TOTAL_RESPONSE_BYTES - 10
        data, _, _ = drive_read(b"x" * 10, total_prior=prior)
        assert len(data) == 10
        with pytest.raises(m._ResponseTooLarge):
            drive_read(b"x" * 11, total_prior=prior)

    def test_no_module_owned_transport_can_reach_network(self):
        source = Path(m.__file__).read_text(encoding="utf-8").lower()
        for needle in ("import socket", "import ssl", "http.client", "urllib.request"):
            assert needle not in source


# ===========================================================================
# C03-01 -- the initial blocking request/status operation, and every
# potentially blocking reader cleanup step, are bounded by the same
# immutable effective min(per-request, global) deadline (Marco Correction 02
# BLOCK finding).
# ===========================================================================


class _ScopeViolationTransport:
    """``perform`` raises a genuine :class:`CapabilityScopeViolation`, first
    optionally burning monotonic time so the effective (and even the global)
    deadline is already past when it raises."""

    def __init__(self, clock=None, advance_ms: int = 0) -> None:
        self._clock = clock
        self._advance_ms = advance_ms
        self.calls = 0

    def perform(self, request, timeout_ms):
        assert isinstance(timeout_ms, int) and timeout_ms > 0
        self.calls += 1
        if self._clock is not None and self._advance_ms:
            self._clock.advance_ms(self._advance_ms)
        raise m.CapabilityScopeViolation("synthetic scope violation")


class TestC0301PerformAndCleanupBudget:
    # --- C03-01-A: perform structurally receives the effective budget. -----

    def test_perform_signature_receives_a_timeout_budget(self):
        params = list(inspect.signature(m.Transport.perform).parameters)
        assert params == ["self", "request", "timeout_ms"]
        assert list(inspect.signature(m.UnavailableTransport.perform).parameters) == [
            "self",
            "request",
            "timeout_ms",
        ]

    def test_first_request_perform_gets_full_but_bounded_positive_budget(self):
        clock = FakeClock()
        _, transport = run_probe(full_discovery_script(), clock=clock)
        assert transport.perform_timeouts  # a request was actually sent
        label, budget = transport.perform_timeouts[0]
        assert label == m.OP_ACCOUNT_LIMITS
        assert 0 < budget <= m.PER_REQUEST_DEADLINE_MS
        assert budget == m.PER_REQUEST_DEADLINE_MS  # full 10 000 ms at t0

    def test_later_request_perform_gets_the_smaller_global_remainder(self):
        # 16 s of signing per request: by request 2 only ~8 s of the 40 s
        # global budget remains -- smaller than the 10 s per-request cap -- so
        # perform must receive ~8 s, never a fresh 10 000 ms.
        clock = FakeClock()
        signer = SlowSigner(clock, advance_ms=16_000)
        script = {
            m.OP_ACCOUNT_LIMITS: resp(account_limits_body()),
            m.OP_API_KEYS: resp(
                {"api_keys": [{"api_key_id": "other", "name": "n", "scopes": ["read"]}]}
            ),
        }
        result, transport = run_probe(script, clock=clock, signer=signer)
        assert result.terminal_outcome == (
            m.B1TerminalOutcome.B1_CURRENT_KEY_NOT_UNIQUELY_MATCHED
        )
        assert transport.perform_timeouts == [
            (m.OP_ACCOUNT_LIMITS, 10_000),
            (m.OP_API_KEYS, 8_000),
        ]
        assert transport.perform_timeouts[1][1] < m.PER_REQUEST_DEADLINE_MS

    def test_perform_not_called_when_the_budget_is_already_exhausted(self):
        # 41 s of signing before request 1: the deadline is already past
        # before the network phase, so perform is never invoked and nothing
        # is resent.
        clock = FakeClock()
        signer = SlowSigner(clock, advance_ms=41_000)
        result, transport = run_probe(
            full_discovery_script(), clock=clock, signer=signer
        )
        assert result.terminal_outcome == m.B1TerminalOutcome.B1_READ_FAILURE
        assert result.detail == "TIMEOUT"
        assert transport.calls == []
        assert transport.perform_timeouts == []
        assert result.manifest.request_count == 1
        assert result.manifest.requests[0].status_class == m.RequestStatusClass.TIMEOUT

    def test_per_request_timer_is_not_reset_after_perform(self):
        # perform burns 4 s of the per-request budget; the first B1-owned body
        # read must then see 6 s -- one continuous timer spans perform rather
        # than a fresh 10 s being started afterwards.
        clock = FakeClock()
        script = full_discovery_script()
        script[m.OP_ACCOUNT_LIMITS] = resp(
            account_limits_body(), pre_ms=4_000, chunk_size=8
        )
        _, transport = run_probe(script, clock=clock)
        assert transport.perform_timeouts[0] == (m.OP_ACCOUNT_LIMITS, 10_000)
        reader = transport.readers[m.OP_ACCOUNT_LIMITS]
        assert reader.calls[0][1] == 6_000

    # --- C03-01-B: the deadline is re-checked immediately after perform. ---

    def test_perform_response_after_deadline_is_read_failure_timeout(self):
        clock = FakeClock()
        script = {m.OP_ACCOUNT_LIMITS: resp(account_limits_body(), pre_ms=10_001)}
        result, transport = run_probe(script, clock=clock)
        assert result.terminal_outcome == m.B1TerminalOutcome.B1_READ_FAILURE
        assert result.detail == "TIMEOUT"
        assert result.manifest.requests[0].status_class == m.RequestStatusClass.TIMEOUT
        # The abandoned reader is neither driven nor -- since no budget
        # remains -- close()d.
        reader = transport.readers[m.OP_ACCOUNT_LIMITS]
        assert reader.calls == []
        assert reader.close_calls == []
        assert reader.closed is False
        assert transport.calls == [m.OP_ACCOUNT_LIMITS]  # no resend

    def test_perform_transport_error_after_deadline_is_timeout_not_transport_failure(
        self,
    ):
        clock = FakeClock()
        script = {m.OP_ACCOUNT_LIMITS: Scripted(kind="TRANSPORT_ERROR", pre_ms=10_001)}
        result, transport = run_probe(script, clock=clock)
        assert result.terminal_outcome == m.B1TerminalOutcome.B1_READ_FAILURE
        assert result.detail == "TIMEOUT"  # not "TRANSPORT_FAILURE"
        assert result.manifest.requests[0].status_class == m.RequestStatusClass.TIMEOUT
        assert len(transport.calls) == 1

    def test_perform_transport_error_within_deadline_stays_transport_failure(self):
        clock = FakeClock()
        script = {m.OP_ACCOUNT_LIMITS: Scripted(kind="TRANSPORT_ERROR")}
        result, transport = run_probe(script, clock=clock)
        assert result.terminal_outcome == m.B1TerminalOutcome.B1_READ_FAILURE
        assert result.detail == "TRANSPORT_FAILURE"
        assert len(transport.calls) == 1

    def test_perform_redirect_after_deadline_is_timeout_not_source_drift(self):
        # The post-perform deadline gate runs BEFORE ordinary status
        # classification (dispatch C03-01-B): a 3xx produced after the
        # effective deadline is READ_FAILURE / TIMEOUT, and the redirect is
        # still never followed and the body never read.
        clock = FakeClock()
        script = {
            m.OP_ACCOUNT_LIMITS: resp(
                None,
                status=302,
                content_type=None,
                extra_headers=(("Location", "https://evil.example/x"),),
                raw_body=b"",
                pre_ms=10_001,
            )
        }
        result, transport = run_probe(script, clock=clock)
        assert result.terminal_outcome == m.B1TerminalOutcome.B1_READ_FAILURE
        assert result.detail == "TIMEOUT"
        assert result.manifest.requests[0].status_class == m.RequestStatusClass.TIMEOUT
        assert len(transport.calls) == 1
        reader = transport.readers[m.OP_ACCOUNT_LIMITS]
        assert reader.calls == []
        assert reader.close_calls == []

    def test_perform_timeout_outcome_is_read_failure_timeout_no_resend(self):
        clock = FakeClock()
        script = {m.OP_ACCOUNT_LIMITS: Scripted(kind="TIMEOUT", pre_ms=3_000)}
        result, transport = run_probe(script, clock=clock)
        assert result.terminal_outcome == m.B1TerminalOutcome.B1_READ_FAILURE
        assert result.detail == "TIMEOUT"
        assert len(transport.calls) == 1

    def test_capability_scope_violation_keeps_precedence_even_past_every_deadline(self):
        clock = FakeClock()
        transport = _ScopeViolationTransport(clock=clock, advance_ms=40_001)
        result = m.execute_b1_account_subaccount_probe(
            credentials_env=make_env(),
            source_record=unrestricted_source(),
            transport=transport,
            signer=FakeSigner(),
            clock=clock,
        )
        # Precedence 1 (B1-TERM-002) is not rewritten to READ_FAILURE by the
        # post-perform deadline gate or by _enforce_global_deadline.
        assert result.terminal_outcome == (
            m.B1TerminalOutcome.B1_CAPABILITY_OR_SCOPE_VIOLATION
        )
        assert transport.calls == 1  # no resend

    # --- C03-01-C: reader cleanup cannot become an unbounded network step. -

    def test_close_receives_a_finite_positive_budget_on_a_clean_run(self):
        clock = FakeClock()
        result, transport = run_probe(full_discovery_script(), clock=clock)
        assert result.terminal_outcome == (
            m.B1TerminalOutcome.B1_EXISTING_NUMBERED_SUBACCOUNT_DISCOVERED
        )
        for label in m.OPERATION_LABELS:
            reader = transport.readers[label]
            assert len(reader.close_calls) == 1
            assert 0 < reader.close_calls[0] <= m.PER_REQUEST_DEADLINE_MS
            assert reader.closed is True

    def test_close_budget_is_recomputed_before_close_from_the_same_anchor(self):
        # 3 s elapsed before the body is read; close must then receive 7 s,
        # proving the deadline is checked/recomputed before close.
        clock = FakeClock()
        script = full_discovery_script()
        script[m.OP_ACCOUNT_LIMITS] = resp(account_limits_body(), pre_ms=3_000)
        _, transport = run_probe(script, clock=clock)
        assert transport.readers[m.OP_ACCOUNT_LIMITS].close_calls == [7_000]

    def test_close_not_called_when_no_positive_budget_remains(self):
        # Two 6 s reads push the clock to 12 s (> the 10 s effective
        # deadline). The B1-owned loop raises before a third read and the
        # deadline-aware cleanup does NOT begin a blocking close.
        clock = FakeClock()
        script = {
            m.OP_ACCOUNT_LIMITS: resp(
                account_limits_body(), chunk_size=8, per_chunk_ms=6_000
            )
        }
        result, transport = run_probe(script, clock=clock)
        assert result.terminal_outcome == m.B1TerminalOutcome.B1_READ_FAILURE
        assert result.detail == "TIMEOUT"
        reader = transport.readers[m.OP_ACCOUNT_LIMITS]
        assert reader.close_calls == []
        assert reader.closed is False
        assert len(transport.calls) == 1  # no resend

    def test_close_crossing_the_deadline_cannot_yield_a_lower_precedence_success(self):
        # close() itself burns past the effective deadline; the post-close
        # deadline re-check downgrades the otherwise-successful request to
        # READ_FAILURE / TIMEOUT -- no success terminal is produced.
        clock = FakeClock()
        script = {m.OP_ACCOUNT_LIMITS: resp(account_limits_body(), close_ms=10_001)}
        result, transport = run_probe(script, clock=clock)
        assert result.terminal_outcome == m.B1TerminalOutcome.B1_READ_FAILURE
        assert result.detail == "TIMEOUT"
        reader = transport.readers[m.OP_ACCOUNT_LIMITS]
        assert reader.close_calls == [10_000]  # close ran with a positive budget
        assert reader.closed is True
        blob = result.summary.to_json_bytes()
        assert b"B1_PRIMARY_ONLY_OBSERVED" not in blob
        assert b"B1_EXISTING_NUMBERED_SUBACCOUNT_DISCOVERED" not in blob
        assert len(transport.calls) == 1  # no resend

    def test_redirect_path_close_is_deadline_bounded_and_no_body_read_occurs(self):
        clock = FakeClock()
        script = {
            m.OP_ACCOUNT_LIMITS: resp(
                None,
                status=302,
                content_type=None,
                extra_headers=(("Location", "https://evil.example/x"),),
                raw_body=b"",
            )
        }
        result, transport = run_probe(script, clock=clock)
        assert result.terminal_outcome == m.B1TerminalOutcome.B1_SOURCE_DRIFT
        reader = transport.readers[m.OP_ACCOUNT_LIMITS]
        assert reader.calls == []  # body never read
        assert reader.close_calls == [m.PER_REQUEST_DEADLINE_MS]  # closed, bounded
        assert len(transport.calls) == 1

    def test_no_deadline_or_transport_branch_triggers_a_resend(self):
        for entry in (
            Scripted(kind="TIMEOUT"),
            Scripted(kind="TIMEOUT", pre_ms=10_001),
            Scripted(kind="TRANSPORT_ERROR"),
            Scripted(kind="TRANSPORT_ERROR", pre_ms=10_001),
            resp(account_limits_body(), pre_ms=10_001),
        ):
            _, transport = run_probe({m.OP_ACCOUNT_LIMITS: entry}, clock=FakeClock())
            assert len(transport.calls) == 1
            assert m.AUTOMATIC_RETRY_COUNT == 0


# ===========================================================================
# C04-01 -- post-close effective-deadline terminal precedence on the
# body-read result paths (Marco Correction 04 finding).
#
# The body-read result must be CAPTURED, exactly one bounded cleanup must run
# on the same immutable effective deadline, and only THEN may terminal
# precedence be evaluated. A close that consumes the remaining budget and
# crosses the per-request deadline must not leave an already-selected
# lower-precedence terminal in place (B1-REQ-004, B1-TERM-002), and must not
# rewrite an already-established higher-precedence terminal.
# ===========================================================================


OVERSIZED_BODY = b'{"api_keys":[]}' + b" " * (
    m.MAX_RESPONSE_BYTES_PER_REQUEST + 1 - len(b'{"api_keys":[]}')
)


class ContractViolatingReader(ScriptReader):
    """A reader that violates the :class:`ResponseBodyReader` contract by
    returning more bytes than the finite ``max_bytes`` B1 requested. B1 fails
    closed with ``_ReadContractError`` rather than trusting it (C02-02)."""

    def read(self, max_bytes: int, timeout_ms: int) -> bytes:
        assert isinstance(max_bytes, int) and max_bytes > 0, max_bytes
        assert isinstance(timeout_ms, int) and timeout_ms > 0, timeout_ms
        self.calls.append((max_bytes, timeout_ms))
        if self._clock is not None and self._per_read_ms:
            self._clock.advance_ms(self._per_read_ms)
        return b"x" * (max_bytes + 1)


class ReaderInjectingTransport(ScriptedTransport):
    """A :class:`ScriptedTransport` that serves a caller-supplied reader for a
    given operation label, so read-contract violations can be exercised
    end-to-end. It still only establishes status + headers and never reads,
    materialises, or returns body bytes itself (C02-02)."""

    def __init__(self, clock, script, *, injected_readers) -> None:
        super().__init__(clock, script)
        self._injected_readers = injected_readers

    def perform(self, request, timeout_ms):
        response = super().perform(request, timeout_ms)
        label = request.operation_label
        injected = self._injected_readers.get(label)
        if injected is None or response.kind != "RESPONSE":
            return response
        self.readers[label] = injected
        return m.TransportResponse(
            kind="RESPONSE",
            status=response.status,
            headers=response.headers,
            reader=injected,
        )


def run_probe_with_transport(transport, *, clock):
    """Run the probe against an explicitly constructed transport. Mirrors
    :func:`run_probe` but does not build the transport itself."""

    result = m.execute_b1_account_subaccount_probe(
        credentials_env=make_env(),
        source_record=unrestricted_source(),
        transport=transport,
        signer=FakeSigner(),
        clock=clock,
    )
    return result, transport


class TestC0401PostCloseDeadlinePrecedence:
    # --- C04-TEST-001 ------------------------------------------------------

    def test_response_too_large_then_close_crossing_deadline_is_timeout(self):
        # _ResponseTooLarge is detected while still inside the 10 s effective
        # budget. The bounded close then burns 10_001 ms and crosses the
        # per-request deadline. B1_READ_FAILURE / TIMEOUT (precedence 4) must
        # outrank the captured B1_AUTHORITATIVE_RESPONSE_MALFORMED
        # projection (precedence 5).
        clock = FakeClock()
        script = {
            m.OP_ACCOUNT_LIMITS: resp(
                None, raw_body=OVERSIZED_BODY, close_ms=10_001
            )
        }
        result, transport = run_probe(script, clock=clock)

        assert result.terminal_outcome == m.B1TerminalOutcome.B1_READ_FAILURE
        assert result.detail == "TIMEOUT"

        reader = transport.readers[m.OP_ACCOUNT_LIMITS]
        # Exactly one bounded cleanup, with the full remaining budget.
        assert reader.close_calls == [10_000]
        assert reader.closed is True

        record = result.manifest.requests[-1]
        assert record.status_class == m.RequestStatusClass.TIMEOUT
        # No fabricated length/hash for an incomplete, oversized body, and no
        # raw body persisted (dispatch Section 7).
        assert record.raw_response_byte_length is None
        assert record.raw_response_sha256 is None
        assert record.local_raw_body_filename is None

        blob = result.summary.to_json_bytes()
        assert b"B1_AUTHORITATIVE_RESPONSE_MALFORMED" not in blob
        assert len(transport.calls) == 1  # zero retry / zero resend

    # --- C04-TEST-002 ------------------------------------------------------

    def test_read_contract_error_then_close_crossing_deadline_is_timeout(self):
        # A read-contract violation is detected inside the budget; the bounded
        # close then crosses the deadline. The subordinate reason must become
        # TIMEOUT, not READ_CONTRACT_VIOLATION.
        clock = FakeClock()
        bad_reader = ContractViolatingReader(b"", clock=clock, close_ms=10_001)
        transport = ReaderInjectingTransport(
            clock,
            {m.OP_ACCOUNT_LIMITS: resp(account_limits_body())},
            injected_readers={m.OP_ACCOUNT_LIMITS: bad_reader},
        )
        result, transport = run_probe_with_transport(transport, clock=clock)

        assert result.terminal_outcome == m.B1TerminalOutcome.B1_READ_FAILURE
        assert result.detail == "TIMEOUT"
        assert result.detail != "READ_CONTRACT_VIOLATION"

        assert bad_reader.close_calls == [10_000]
        assert bad_reader.closed is True

        record = result.manifest.requests[-1]
        assert record.status_class == m.RequestStatusClass.TIMEOUT
        assert record.raw_response_byte_length is None
        assert record.raw_response_sha256 is None
        assert record.local_raw_body_filename is None
        assert len(transport.calls) == 1

    # --- C04-TEST-003 ------------------------------------------------------

    def test_response_too_large_with_close_inside_deadline_stays_malformed(self):
        # Same oversized body, but the bounded close completes well inside the
        # deadline: the captured result projects normally as
        # B1_AUTHORITATIVE_RESPONSE_MALFORMED with the subordinate
        # RESPONSE_TOO_LARGE evidence class.
        clock = FakeClock()
        script = {
            m.OP_ACCOUNT_LIMITS: resp(None, raw_body=OVERSIZED_BODY, close_ms=5)
        }
        result, transport = run_probe(script, clock=clock)

        assert result.terminal_outcome == (
            m.B1TerminalOutcome.B1_AUTHORITATIVE_RESPONSE_MALFORMED
        )
        record = result.manifest.requests[-1]
        assert record.status_class == m.RequestStatusClass.RESPONSE_TOO_LARGE
        assert record.raw_response_byte_length is None
        assert record.raw_response_sha256 is None
        assert record.local_raw_body_filename is None

        reader = transport.readers[m.OP_ACCOUNT_LIMITS]
        assert reader.close_calls == [10_000]
        assert reader.closed is True
        assert len(transport.calls) == 1

    def test_read_contract_error_with_close_inside_deadline_keeps_its_reason(self):
        # The mirror of C04-TEST-003 for the read-contract path: inside the
        # deadline the captured result keeps READ_CONTRACT_VIOLATION.
        clock = FakeClock()
        bad_reader = ContractViolatingReader(b"", clock=clock, close_ms=5)
        transport = ReaderInjectingTransport(
            clock,
            {m.OP_ACCOUNT_LIMITS: resp(account_limits_body())},
            injected_readers={m.OP_ACCOUNT_LIMITS: bad_reader},
        )
        result, _ = run_probe_with_transport(transport, clock=clock)

        assert result.terminal_outcome == m.B1TerminalOutcome.B1_READ_FAILURE
        assert result.detail == "READ_CONTRACT_VIOLATION"
        assert result.manifest.requests[-1].status_class == (
            m.RequestStatusClass.TRANSPORT_FAILURE
        )
        assert bad_reader.close_calls == [10_000]

    # --- C04-TEST-004 ------------------------------------------------------

    def test_source_drift_remains_controlling_when_close_crosses_deadline(self):
        # A 3xx establishes B1_SOURCE_DRIFT (precedence 3) BEFORE any body
        # read. Its bounded close crosses the deadline; the post-close
        # deadline gate must NOT rewrite it to the lower-precedence
        # B1_READ_FAILURE / TIMEOUT (precedence 4).
        clock = FakeClock()
        script = {
            m.OP_ACCOUNT_LIMITS: resp(
                None,
                status=302,
                content_type=None,
                extra_headers=(("Location", "https://evil.example/x"),),
                raw_body=b"",
                close_ms=10_001,
            )
        }
        result, transport = run_probe(script, clock=clock)

        assert result.terminal_outcome == m.B1TerminalOutcome.B1_SOURCE_DRIFT
        assert result.detail == "3xx redirect not followed"

        reader = transport.readers[m.OP_ACCOUNT_LIMITS]
        assert reader.calls == []  # body never read, redirect never followed
        assert reader.close_calls == [m.PER_REQUEST_DEADLINE_MS]
        assert reader.closed is True

        assert result.manifest.requests[-1].status_class == (
            m.RequestStatusClass.REDIRECT_3XX
        )
        assert len(transport.calls) == 1

    def test_capability_scope_violation_outranks_a_later_deadline_crossing(self):
        # Precedence 1 is likewise never rewritten by a deadline crossing.
        clock = FakeClock()

        class ViolatingTransport(ScriptedTransport):
            def perform(self, request, timeout_ms):
                self.calls.append(request.operation_label)
                clock.advance_ms(10_001)
                raise m.CapabilityScopeViolation("synthetic scope violation")

        transport = ViolatingTransport(
            clock, {m.OP_ACCOUNT_LIMITS: resp(account_limits_body())}
        )
        result, _ = run_probe_with_transport(transport, clock=clock)
        assert result.terminal_outcome == (
            m.B1TerminalOutcome.B1_CAPABILITY_OR_SCOPE_VIOLATION
        )

    # --- Structural guarantee ---------------------------------------------

    def test_body_read_block_defers_projection_until_after_bounded_close(self):
        # The defect was structural: a `return` inside an `except` selects the
        # terminal before `finally` runs the bounded close. Assert that the
        # B1-owned body-read statement contains no `return` at all, so the
        # captured result can only be projected after cleanup.
        source = inspect.getsource(m._perform_one_request)
        marker = "body_bytes = _read_response_body("
        assert marker in source
        start = source.index(marker)
        end = source.index("if read_error is not None:", start)
        block = source[start:end]
        assert "return" not in block
        assert "_safe_close_reader(" in block

    def test_exactly_one_bounded_close_per_body_read_path(self):
        # Success, oversized, and read-contract paths each perform exactly one
        # bounded close -- cleanup is never duplicated or skipped.
        clock = FakeClock()
        _, transport = run_probe(full_discovery_script(), clock=clock)
        for label in m.OPERATION_LABELS:
            assert len(transport.readers[label].close_calls) == 1

        clock = FakeClock()
        script = {m.OP_ACCOUNT_LIMITS: resp(None, raw_body=OVERSIZED_BODY)}
        _, transport = run_probe(script, clock=clock)
        assert len(transport.readers[m.OP_ACCOUNT_LIMITS].close_calls) == 1

        clock = FakeClock()
        bad_reader = ContractViolatingReader(b"", clock=clock)
        transport = ReaderInjectingTransport(
            clock,
            {m.OP_ACCOUNT_LIMITS: resp(account_limits_body())},
            injected_readers={m.OP_ACCOUNT_LIMITS: bad_reader},
        )
        run_probe_with_transport(transport, clock=clock)
        assert len(bad_reader.close_calls) == 1


# ===========================================================================
# C01-03 -- evidence output root must be external to the repository
# (Marco finding 3).
# ===========================================================================


class TestC0103EvidenceOutputRoot:
    def _result(self):
        result, _ = run_probe(full_discovery_script())
        return result

    def test_empty_or_blank_root_rejected(self):
        result = self._result()
        for bad in ("", "   ", None):
            with pytest.raises(m.EvidenceOutputRootError):
                result.write_evidence(bad)
        # EvidenceOutputRootError is still a ValueError (historical contract).
        with pytest.raises(ValueError):
            result.write_evidence("")

    def test_repository_root_rejected_before_mutation(self):
        result = self._result()
        repo_root = m._canonical_repository_root()
        with pytest.raises(m.EvidenceOutputRootError):
            result.write_evidence(str(repo_root))
        assert not (repo_root / m.SANITIZED_SUMMARY_FILENAME).exists()
        assert not (repo_root / m.EVIDENCE_MANIFEST_FILENAME).exists()

    def test_repository_descendant_rejected_before_mutation(self):
        result = self._result()
        repo_root = m._canonical_repository_root()
        descendant = repo_root / "src" / "arb" / "venues" / "kalshi"
        with pytest.raises(m.EvidenceOutputRootError):
            result.write_evidence(str(descendant))
        assert not (descendant / m.SANITIZED_SUMMARY_FILENAME).exists()
        assert not (descendant / m.EVIDENCE_MANIFEST_FILENAME).exists()

    def test_relative_dot_path_into_repo_rejected(self, monkeypatch):
        result = self._result()
        repo_root = m._canonical_repository_root()
        monkeypatch.chdir(repo_root)
        with pytest.raises(m.EvidenceOutputRootError):
            result.write_evidence("./tests")

    def test_summary_and_manifest_write_guarded_independently(self):
        result = self._result()
        repo_root = str(m._canonical_repository_root())
        with pytest.raises(m.EvidenceOutputRootError):
            result.summary.write(repo_root)
        with pytest.raises(m.EvidenceOutputRootError):
            result.manifest.write(repo_root)

    def test_external_temporary_root_permitted(self, tmp_path):
        result = self._result()
        summary_path, manifest_path, raw_paths = result.write_evidence(str(tmp_path))
        assert Path(summary_path).is_file()
        assert Path(manifest_path).is_file()
        assert len(raw_paths) == 4 and all(Path(p).is_file() for p in raw_paths)

    def test_execute_boundary_takes_no_output_root_and_never_persists(self):
        # C02-01 evidence-write boundary: the execute boundary neither accepts
        # an output root nor performs any filesystem write. Containment now
        # lives entirely in the explicit persistence API.
        exec_params = inspect.signature(
            m.execute_b1_account_subaccount_probe
        ).parameters
        assert "output_root" not in exec_params
        finish_params = inspect.signature(m._finish).parameters
        assert "output_root" not in finish_params

        result, transport = run_probe(full_discovery_script())
        repo_root = m._canonical_repository_root()
        with pytest.raises(m.EvidenceOutputRootError):
            result.write_evidence(str(repo_root))
        assert not (repo_root / m.SANITIZED_SUMMARY_FILENAME).exists()
        assert not (repo_root / m.EVIDENCE_MANIFEST_FILENAME).exists()

    def test_canonical_repository_root_points_at_repo(self):
        root = m._canonical_repository_root()
        assert (root / "src" / "arb" / "venues" / "kalshi"
                / "account_subaccount_probe.py").is_file()


# ===========================================================================
# C01-04 -- balance duplicate identity is lexical, not Decimal-equivalent
# (Marco finding 4).
# ===========================================================================


class TestC0104BalanceLexicalDuplicate:
    def test_same_lexical_row_repeated_is_canonicalized_once(self):
        rows = [
            brow(0, balance="0.00", ts=3),
            brow(0, balance="0.00", ts=3),
            brow(2, balance="1.250000", ts=9),
            brow(2, balance="1.250000", ts=9),
        ]
        parsed = m.parse_subaccount_balances(balances_body(rows))
        assert len(parsed) == 2
        assert {r.subaccount_number for r in parsed} == {0, 2}

    def test_1p0_vs_1p00_conflict(self):
        rows = [brow(2, idx=0, balance="1.0", ts=5), brow(2, idx=0, balance="1.00", ts=5)]
        with pytest.raises(m.B1ProbeError):
            m.parse_subaccount_balances(balances_body(rows))

    def test_zero_vs_negative_zero_conflict(self):
        rows = [brow(0, idx=0, balance="0", ts=1), brow(0, idx=0, balance="-0", ts=1)]
        with pytest.raises(m.B1ProbeError):
            m.parse_subaccount_balances(balances_body(rows))

    def test_numerically_different_duplicate_conflict(self):
        rows = [brow(0, idx=0, balance="0", ts=1), brow(0, idx=0, balance="5.00", ts=1)]
        with pytest.raises(m.B1ProbeError):
            m.parse_subaccount_balances(balances_body(rows))

    def test_same_lexical_balance_but_different_updated_ts_conflicts(self):
        rows = [brow(0, idx=0, balance="0", ts=1), brow(0, idx=0, balance="0", ts=2)]
        with pytest.raises(m.B1ProbeError):
            m.parse_subaccount_balances(balances_body(rows))

    def test_decimal_still_used_for_zero_nonzero_classification(self):
        # Lexically different, numerically equal -> both NONZERO.
        _, cls_a = m.parse_balance_decimal("1.0")
        _, cls_b = m.parse_balance_decimal("1.00")
        assert cls_a == cls_b == m.BalanceClass.NONZERO
        # Lexically different zero forms -> both ZERO.
        _, cls_c = m.parse_balance_decimal("0")
        _, cls_d = m.parse_balance_decimal("-0")
        assert cls_c == cls_d == m.BalanceClass.ZERO
        rows = m.parse_subaccount_balances(
            balances_body([brow(0, balance="0.000000"), brow(3, balance="0.010000")])
        )
        classes = m._summarize_balance_classes(rows)
        assert dict(classes) == {0: m.BalanceClass.ZERO, 3: m.BalanceClass.NONZERO}

    def test_lexical_balance_text_never_in_sanitized_summary(self):
        script = full_discovery_script()
        script[m.OP_SUBACCOUNT_BALANCES] = resp(
            balances_body([brow(0, balance="0"), brow(2, balance="7.011001")])
        )
        result, _ = run_probe(script)
        blob = result.summary.to_json_bytes()
        assert b"7.011001" not in blob
        summary = json.loads(blob)
        classes = {
            e["subaccount_number"]: e["class"]
            for e in summary["enumeration"]["balance_classes"]
        }
        assert classes == {0: "ZERO", 2: "NONZERO"}

    def test_conflicting_lexical_duplicate_via_execute(self):
        script = full_discovery_script(numbered=(2,))
        script[m.OP_SUBACCOUNT_BALANCES] = resp(
            balances_body(
                [
                    brow(0, idx=0, balance="0", ts=1),
                    brow(2, idx=0, balance="1.0", ts=1),
                    brow(2, idx=0, balance="1.00", ts=1),
                ]
            )
        )
        result, _ = run_probe(script)
        assert result.terminal_outcome == (
            m.B1TerminalOutcome.B1_AUTHORITATIVE_RESPONSE_MALFORMED
        )

    def test_balance_row_retains_lexical_text(self):
        rows = m.parse_subaccount_balances(
            balances_body([brow(0, balance="0"), brow(1, balance="2.500000")])
        )
        texts = {r.subaccount_number: r.balance_text for r in rows}
        assert texts == {0: "0", 1: "2.500000"}


# ===========================================================================
# Signing boundary -- canonical ARB authenticated-GET RSA-PSS profile
# (Section 7), exercised offline with synthetic key material.
# ===========================================================================


class TestSigningBoundary:
    def test_signing_message_is_timestamp_method_path(self):
        plan = m.build_request_plan_sequence()[0]
        sm = m.build_signing_message(plan, "1724800000000")
        assert sm.message_bytes == b"1724800000000GET/trade-api/v2/account/limits"
        assert "?" not in sm.full_path

    def test_non_canonical_timestamp_rejected(self):
        plan = m.build_request_plan_sequence()[0]
        for bad in ("0123", "-1", "12.0", "abc", "", "0"):
            with pytest.raises(m.SigningContractError):
                m.build_signing_message(plan, bad)

    def test_rsa_pss_file_signer_matches_canonical_profile(self, tmp_path):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_path = tmp_path / "synthetic_key.pem"
        key_path.write_bytes(pem)

        signer = m.RsaPssSha256FileSigner(str(key_path))
        plan = m.build_request_plan_sequence()[1]
        sm = m.build_signing_message(plan, "1724800000001")
        signature = signer.sign(sm.message_bytes)

        key.public_key().verify(
            signature,
            sm.message_bytes,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=hashes.SHA256().digest_size,
            ),
            hashes.SHA256(),
        )

    def test_non_rsa_key_rejected(self, tmp_path):
        from cryptography.hazmat.primitives.asymmetric import ed25519

        key = ed25519.Ed25519PrivateKey.generate()
        pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_path = tmp_path / "ed25519.pem"
        key_path.write_bytes(pem)
        with pytest.raises(m.SigningContractError):
            m.RsaPssSha256FileSigner(str(key_path)).sign(b"msg")

    def test_signer_errors_do_not_leak_key_material(self, tmp_path):
        key_path = tmp_path / "not_a_key.pem"
        key_path.write_bytes(b"-----BEGIN PRIVATE KEY-----\nnonsense\n-----END PRIVATE KEY-----\n")
        try:
            m.RsaPssSha256FileSigner(str(key_path)).sign(b"msg")
        except m.SigningContractError as exc:
            assert "nonsense" not in str(exc)
            assert "BEGIN PRIVATE KEY" not in str(exc)
        else:  # pragma: no cover
            pytest.fail("expected SigningContractError")


# ===========================================================================
# Default no-network posture.
# ===========================================================================


class TestNoNetworkByDefault:
    def test_missing_transport_cannot_reach_network(self):
        result = m.execute_b1_account_subaccount_probe(
            credentials_env=make_env(),
            source_record=unrestricted_source(),
            signer=FakeSigner(),
            clock=FakeClock(),
        )
        assert result.terminal_outcome == (
            m.B1TerminalOutcome.B1_CAPABILITY_OR_SCOPE_VIOLATION
        )
        assert result.manifest.request_count == 1

    def test_unavailable_transport_raises(self):
        with pytest.raises(m.CapabilityScopeViolation):
            m.UnavailableTransport().perform(object(), 10_000)


# ===========================================================================
# Correction 02 -- deterministic canonical source-binding record (BIND-01..08)
# and decisive negative controls N01-N05
# (KALSHI_DEMO_ROUTE_B_B1_CURRENT_SOURCE_BINDING_AND_EXECUTION_EVIDENCE_CORRECTION_02).
#
# The blocked predecessor (d6bb5dd) let SourceEvidenceBinding.record_sha256 be
# an opaque caller-supplied digest, so an UNRESTRICTED record and a NOT_EXPOSED
# record could emit the SAME active binding identity. Correction 02 derives the
# active non-authoring hash from a deterministic canonical record over full
# provenance + full material B1 semantics.
# ===========================================================================


def _canon_json_bytes(obj) -> bytes:
    return json.dumps(
        obj, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _expected_canonical_binding_record(rec: m.TaskCurrentSourceRecord) -> dict:
    """An INDEPENDENT reconstruction of the canonical binding record from the
    record's public fields (BIND-03 / N03) -- must equal
    ``rec.canonical_binding_record()``."""

    b = rec.evidence_binding
    ops = []
    for label in m.OPERATION_LABELS:
        op = rec.operation(label)
        ops.append(
            {
                "label": label,
                "method": op.method,
                "path": op.path,
                "required_top_level": list(op.required_top_level),
            }
        )
    return {
        "binding_record_schema_revision": b.binding_record_schema_revision,
        "binding_name": b.name,
        "provenance": {
            "source_url": b.source_url,
            "raw_source_bytes": b.raw_source_bytes,
            "raw_source_sha256": b.raw_source_sha256,
            "openapi_format": b.openapi_format,
            "openapi_info_version": b.openapi_info_version,
            "observed_at_utc": b.observed_at_utc,
            "fresh_raw_openapi_status": b.fresh_raw_openapi_status,
            "historical_openapi_context_sha256": b.historical_openapi_context_sha256,
        },
        "semantics": {
            "demo_rest_base_url": rec.demo_rest_base_url,
            "operations": ops,
            "api_keys_absent_subaccount_semantics": (
                rec.api_keys_absent_subaccount_semantics
            ),
            "subaccount_number_min": rec.subaccount_number_min,
            "subaccount_number_max": rec.subaccount_number_max,
            "restricted_key_error_signature": {
                "field_name": rec.restricted_key_error_signature.field_name,
                "expected_value": rec.restricted_key_error_signature.expected_value,
            },
            "signature_path_excludes_query": rec.signature_path_excludes_query,
            "declares_unresolved_conflict": rec.declares_unresolved_conflict,
            "record_label": rec.record_label,
        },
    }


_MANIFEST_KEYS = {
    "schema_revision",
    "task_id",
    "environment",
    "demo_rest_base_url",
    "source_binding_name",
    "source_binding_record_sha256",
    "started_at_utc",
    "completed_at_utc",
    "request_count",
    "retry_count",
    "redirect_count",
    "requests",
}
_MANIFEST_REQUEST_KEYS = {
    "sequence",
    "method",
    "path",
    "http_status",
    "status_class",
    "raw_response_byte_length",
    "raw_response_sha256",
    "observed_at_utc",
    "local_raw_body_filename",
}
_SUMMARY_KEYS = {
    "schema_revision",
    "task_id",
    "environment",
    "demo_rest_base_url",
    "source_binding",
    "terminal_outcome",
    "next_route_class",
    "request_count",
    "retry_count",
    "redirect_count",
    "api_usage",
    "current_key",
    "enumeration",
    "create_subaccount",
    "historical_primary",
    "negative_theorems",
    "evidence_manifest",
}
_SUMMARY_SOURCE_BINDING_KEYS = {
    "name",
    "record_sha256",
    "observed_at_utc",
    "fresh_raw_openapi_status",
    "historical_openapi_context_sha256",
}


def _op_mutation(rec, *, field, value):
    ops = tuple(
        dataclasses.replace(op, **{field: value}) if op.label == m.OP_API_KEYS else op
        for op in rec.operations
    )
    return dataclasses.replace(rec, operations=ops)


class TestBIND01DeterministicCanonicalRecord:
    def test_binding_class_carries_no_caller_supplied_hash(self):
        names = {f.name for f in dataclasses.fields(m.SourceEvidenceBinding)}
        assert "record_sha256" not in names

    def test_active_hash_is_sha256_of_canonical_bytes(self):
        rec = current_openapi_source()
        raw = rec.canonical_binding_record_bytes()
        assert rec.binding_record_sha256 == hashlib.sha256(raw).hexdigest()
        assert rec.binding_record_sha256 != AUTHORING_RECORD_SHA256

    def test_serialization_is_canonical(self):
        rec = current_openapi_source()
        raw = rec.canonical_binding_record_bytes()
        # tight separators, ASCII only, sorted keys
        assert b", " not in raw and b'": ' not in raw
        raw.decode("ascii")  # would raise if non-ASCII
        assert raw == _canon_json_bytes(rec.canonical_binding_record())

    def test_two_records_differing_only_in_a_material_field_differ_in_hash(self):
        a = current_openapi_source(record_label="LABEL_A")
        b = current_openapi_source(record_label="LABEL_B")
        assert a.binding_record_sha256 != b.binding_record_sha256


class TestBIND02MaterialSemanticCompleteness:
    def test_canonical_record_top_level_shape(self):
        cbr = current_openapi_source().canonical_binding_record()
        assert set(cbr) == {
            "binding_record_schema_revision",
            "binding_name",
            "provenance",
            "semantics",
        }
        assert cbr["binding_record_schema_revision"] == m.BINDING_RECORD_SCHEMA_REVISION

    def test_provenance_and_semantics_fields_present(self):
        cbr = current_openapi_source().canonical_binding_record()
        assert set(cbr["provenance"]) == {
            "source_url",
            "raw_source_bytes",
            "raw_source_sha256",
            "openapi_format",
            "openapi_info_version",
            "observed_at_utc",
            "fresh_raw_openapi_status",
            "historical_openapi_context_sha256",
        }
        assert set(cbr["semantics"]) == {
            "demo_rest_base_url",
            "operations",
            "api_keys_absent_subaccount_semantics",
            "subaccount_number_min",
            "subaccount_number_max",
            "restricted_key_error_signature",
            "signature_path_excludes_query",
            "declares_unresolved_conflict",
            "record_label",
        }

    def test_operations_ordered_by_operation_labels(self):
        cbr = current_openapi_source().canonical_binding_record()
        assert [o["label"] for o in cbr["semantics"]["operations"]] == list(
            m.OPERATION_LABELS
        )

    def test_no_duplicate_source_of_truth_for_observed_at(self):
        rec_fields = {f.name for f in dataclasses.fields(m.TaskCurrentSourceRecord)}
        assert "observed_at_utc" not in rec_fields  # lives only on the binding


class TestBIND03HashRecomputation:
    def test_independent_recompute_matches_emitted_active_hash(self):
        rec = current_openapi_source()
        expected = _expected_canonical_binding_record(rec)
        assert rec.canonical_binding_record() == expected
        expected_hash = hashlib.sha256(_canon_json_bytes(expected)).hexdigest()
        assert rec.binding_record_sha256 == expected_hash

        result, _ = run_probe(
            full_discovery_script(
                api_keys=api_keys_body(include_subaccount_null=True)
            ),
            source=rec,
        )
        manifest = json.loads(result.manifest.to_json_bytes())
        summary = json.loads(result.summary.to_json_bytes())
        assert manifest["source_binding_record_sha256"] == expected_hash
        assert summary["source_binding"]["record_sha256"] == expected_hash


class TestBIND04SemanticBindingCongruencePreNetwork:
    def test_structurally_invalid_identity_is_drift_pre_network(self):
        good = current_openapi_binding()
        bad = {
            "source_url_not_https": dataclasses.replace(good, source_url="ftp://x/y"),
            "raw_bytes_non_positive": dataclasses.replace(good, raw_source_bytes=0),
            "raw_sha_not_hex": dataclasses.replace(good, raw_source_sha256="nope"),
            "raw_sha_uppercase": dataclasses.replace(
                good, raw_source_sha256=CURRENT_OPENAPI_RAW_SHA256.upper()
            ),
            "historical_not_hex": dataclasses.replace(
                good, historical_openapi_context_sha256="zz"
            ),
            "observed_not_rfc3339": dataclasses.replace(
                good, observed_at_utc="last tuesday"
            ),
            "fresh_status_blank": dataclasses.replace(
                good, fresh_raw_openapi_status="   "
            ),
            "openapi_format_blank": dataclasses.replace(good, openapi_format=""),
            "openapi_version_blank": dataclasses.replace(
                good, openapi_info_version=""
            ),
            "unsupported_schema_rev": dataclasses.replace(
                good, binding_record_schema_revision=999
            ),
            "name_blank": dataclasses.replace(good, name="  "),
        }
        for label, binding in bad.items():
            assert binding.validate() != (), label
            src = current_openapi_source(binding=binding)
            assert (
                src.evaluate_against_reviewed_contract().status
                == m.SourceEvaluationStatus.DRIFT
            ), label
            result, transport = run_probe(full_discovery_script(), source=src)
            assert result.terminal_outcome == m.B1TerminalOutcome.B1_SOURCE_DRIFT, label
            assert result.manifest.request_count == 0, label
            assert transport.calls == [], label
            manifest = json.loads(result.manifest.to_json_bytes())
            summary = json.loads(result.summary.to_json_bytes())
            assert manifest["source_binding_name"] == "UNUSABLE_SOURCE_EVIDENCE_BINDING", label
            assert manifest["source_binding_record_sha256"] == "0" * 64, label
            assert summary["source_binding"]["name"] == "UNUSABLE_SOURCE_EVIDENCE_BINDING", label
            blob = result.manifest.to_json_bytes() + result.summary.to_json_bytes()
            assert AUTHORING_RECORD_SHA256.encode() not in blob, label
            assert CURRENT_OPENAPI_RAW_SHA256.encode() not in blob, label

    def test_absent_evidence_binding_is_rejected(self):
        src = dataclasses.replace(current_openapi_source(), evidence_binding=None)
        assert (
            src.evaluate_against_reviewed_contract().status
            == m.SourceEvaluationStatus.DRIFT
        )
        result, transport = run_probe(full_discovery_script(), source=src)
        assert result.terminal_outcome == m.B1TerminalOutcome.B1_SOURCE_DRIFT
        assert result.manifest.request_count == 0
        assert transport.calls == []
        assert json.loads(result.manifest.to_json_bytes())["source_binding_name"] == (
            "UNUSABLE_SOURCE_EVIDENCE_BINDING"
        )

    def test_contract_drift_with_valid_identity_keeps_derived_identity(self):
        drifted = dataclasses.replace(
            current_openapi_source(), subaccount_number_max=32
        )
        assert (
            drifted.evaluate_against_reviewed_contract().status
            == m.SourceEvaluationStatus.DRIFT
        )
        result, _ = run_probe(full_discovery_script(), source=drifted)
        assert result.terminal_outcome == m.B1TerminalOutcome.B1_SOURCE_DRIFT
        manifest = json.loads(result.manifest.to_json_bytes())
        assert manifest["source_binding_record_sha256"] == drifted.binding_record_sha256
        assert manifest["source_binding_record_sha256"] != "0" * 64
        assert manifest["source_binding_name"] == CURRENT_OPENAPI_BINDING_NAME

    def test_no_new_terminal_outcome_added(self):
        assert set(m.B1TerminalOutcome) == {
            m.B1TerminalOutcome.B1_EXISTING_NUMBERED_SUBACCOUNT_DISCOVERED,
            m.B1TerminalOutcome.B1_PRIMARY_ONLY_OBSERVED,
            m.B1TerminalOutcome.B1_ACCOUNT_WIDE_ENUMERATION_NOT_PROVEN_WITH_CURRENT_KEY,
            m.B1TerminalOutcome.B1_CURRENT_KEY_NOT_UNIQUELY_MATCHED,
            m.B1TerminalOutcome.B1_READ_CAPABILITY_INSUFFICIENT,
            m.B1TerminalOutcome.B1_SUBACCOUNT_ENUMERATION_DISAGREEMENT,
            m.B1TerminalOutcome.B1_OFFICIAL_SOURCE_CONFLICT,
            m.B1TerminalOutcome.B1_AUTHORITATIVE_RESPONSE_MALFORMED,
            m.B1TerminalOutcome.B1_READ_FAILURE,
            m.B1TerminalOutcome.B1_SOURCE_DRIFT,
            m.B1TerminalOutcome.B1_CAPABILITY_OR_SCOPE_VIOLATION,
        }


class TestBIND05AuthoringLegacyPreservation:
    def test_authoring_congruent_record_emits_964056df(self):
        result, _ = run_probe(full_discovery_script(), source=not_exposed_source())
        manifest = json.loads(result.manifest.to_json_bytes())
        summary = json.loads(result.summary.to_json_bytes())
        assert manifest["source_binding_name"] == AUTHORING_BINDING_NAME
        assert manifest["source_binding_record_sha256"] == AUTHORING_RECORD_SHA256
        assert summary["source_binding"] == {
            "name": AUTHORING_BINDING_NAME,
            "record_sha256": AUTHORING_RECORD_SHA256,
            "observed_at_utc": "2026-08-27T20:02:16Z",
            "fresh_raw_openapi_status": m.FRESH_RAW_OPENAPI_STATUS,
            "historical_openapi_context_sha256": HISTORICAL_3280_SHA256,
        }

    def test_authoring_hash_is_over_the_embedded_reviewed_record(self):
        rec = m.authoring_task_current_source_record()
        assert rec.evaluate_against_reviewed_contract().status == (
            m.SourceEvaluationStatus.OK
        )
        assert rec.binding_record_sha256 == AUTHORING_RECORD_SHA256
        raw = m.SOURCE_BINDING_RECORD_JSON.encode("utf-8")
        assert hashlib.sha256(raw).hexdigest() == AUTHORING_RECORD_SHA256
        assert m.verify_source_binding_record(raw) is True
        assert m.SOURCE_BINDING_RECORD_BYTES == 3307
        assert m.SOURCE_BINDING_NAME == AUTHORING_BINDING_NAME

    def test_n04_authoring_hash_with_changed_material_semantic_drifts_pre_network(self):
        base = m.authoring_task_current_source_record()  # keeps authoring-legacy binding
        mutations = {
            "semantic": dataclasses.replace(
                base, api_keys_absent_subaccount_semantics="UNRESTRICTED"
            ),
            "record_label": dataclasses.replace(base, record_label="something-else"),
            "subaccount_max": dataclasses.replace(base, subaccount_number_max=32),
            "operation_method": _op_mutation(base, field="method", value="POST"),
        }
        for label, rec in mutations.items():
            assert (
                rec.evaluate_against_reviewed_contract().status
                == m.SourceEvaluationStatus.DRIFT
            ), label
            result, transport = run_probe(full_discovery_script(), source=rec)
            assert result.terminal_outcome == m.B1TerminalOutcome.B1_SOURCE_DRIFT, label
            assert result.manifest.request_count == 0, label
            assert transport.calls == [], label
            blob = result.manifest.to_json_bytes() + result.summary.to_json_bytes()
            assert AUTHORING_RECORD_SHA256.encode() not in blob, label
            assert json.loads(result.manifest.to_json_bytes())["source_binding_name"] == (
                "UNUSABLE_SOURCE_EVIDENCE_BINDING"
            ), label

    def test_n04_authoring_name_with_non_authoring_provenance_drifts(self):
        rec = dataclasses.replace(
            not_exposed_source(),
            evidence_binding=dataclasses.replace(
                m.AUTHORING_SOURCE_EVIDENCE_BINDING,
                source_url="https://docs.kalshi.com/openapi.yaml",
            ),
        )
        assert (
            rec.evaluate_against_reviewed_contract().status
            == m.SourceEvaluationStatus.DRIFT
        )
        result, transport = run_probe(full_discovery_script(), source=rec)
        assert result.terminal_outcome == m.B1TerminalOutcome.B1_SOURCE_DRIFT
        assert transport.calls == []

    def test_new_non_authoring_serialization_not_forced_to_legacy_hash(self):
        assert current_openapi_source().binding_record_sha256 != AUTHORING_RECORD_SHA256


class TestBIND06CurrentSourceProvenanceTimestamp:
    def test_no_fabricated_empirical_timestamp_in_module(self):
        src = Path(m.__file__).read_text(encoding="utf-8")
        assert _FORBIDDEN_FABRICATED_TS not in src
        # The only production observed_at literal is the genuine authoring
        # rendered-source observation (B1-SRC-001).
        assert m.SOURCE_OBSERVED_AT_UTC == "2026-08-27T20:02:16Z"

    def test_no_fabricated_empirical_timestamp_in_tests(self):
        tsrc = Path(__file__).read_text(encoding="utf-8")
        assert _FORBIDDEN_FABRICATED_TS not in tsrc

    def test_synthetic_test_timestamp_is_clearly_marked_and_not_exported(self):
        assert SYNTHETIC_TEST_ONLY_OBSERVED_AT == "2000-01-01T00:00:00Z"
        assert "SYNTHETIC" in "SYNTHETIC_TEST_ONLY_OBSERVED_AT"
        assert "2026" not in SYNTHETIC_TEST_ONLY_OBSERVED_AT
        assert current_openapi_binding().observed_at_utc == SYNTHETIC_TEST_ONLY_OBSERVED_AT
        assert not hasattr(m, "SYNTHETIC_TEST_ONLY_OBSERVED_AT")

    def test_binding_requires_explicit_observed_at_no_empirical_default(self):
        f = {fld.name: fld for fld in dataclasses.fields(m.SourceEvidenceBinding)}
        assert f["observed_at_utc"].default is dataclasses.MISSING
        assert f["observed_at_utc"].default_factory is dataclasses.MISSING

    def test_committed_provenance_equals_binding_provenance(self):
        rec = current_openapi_source()
        cbr = rec.canonical_binding_record()
        assert cbr["provenance"] == rec.evidence_binding.provenance_record()
        assert cbr["provenance"]["raw_source_sha256"] == CURRENT_OPENAPI_RAW_SHA256
        assert cbr["provenance"]["raw_source_bytes"] == CURRENT_OPENAPI_RAW_BYTES
        assert cbr["provenance"]["source_url"] == CURRENT_OPENAPI_SOURCE_URL
        assert cbr["provenance"]["openapi_info_version"] == "3.29.0"

    def test_raw_openapi_sha_is_not_the_binding_record_hash(self):
        assert current_openapi_source().binding_record_sha256 != CURRENT_OPENAPI_RAW_SHA256


class TestBIND07DecisiveNegativeControls:
    def test_n01_same_binding_different_absent_null_semantic(self):
        b = current_openapi_binding()
        a_rec = current_openapi_source(binding=b, semantics="UNRESTRICTED",
                                      record_label="SAME")
        b_rec = current_openapi_source(binding=b, semantics="NOT_EXPOSED",
                                      record_label="SAME")
        # Both structurally valid, but they MUST NOT share the active hash.
        assert a_rec.binding_record_sha256 != b_rec.binding_record_sha256
        ra, _ = run_probe(
            full_discovery_script(api_keys=api_keys_body(include_subaccount_null=True)),
            source=a_rec,
        )
        rb, _ = run_probe(
            {
                m.OP_ACCOUNT_LIMITS: resp(account_limits_body()),
                m.OP_API_KEYS: resp(api_keys_body(include_subaccount_null=True)),
            },
            source=b_rec,
        )
        ha = json.loads(ra.manifest.to_json_bytes())["source_binding_record_sha256"]
        hb = json.loads(rb.manifest.to_json_bytes())["source_binding_record_sha256"]
        assert ha != hb
        assert ha != AUTHORING_RECORD_SHA256 and hb != AUTHORING_RECORD_SHA256

    def test_n02_every_material_semantic_class_changes_hash_or_invalidates(self):
        rec = current_openapi_source()
        base_hash = rec.binding_record_sha256

        def changed_or_drift(r):
            return (
                r.binding_record_sha256 != base_hash
                or r.evaluate_against_reviewed_contract().status
                == m.SourceEvaluationStatus.DRIFT
            )

        mutations = [
            _op_mutation(rec, field="method", value="POST"),
            _op_mutation(rec, field="path", value="/api_keys_v2"),
            _op_mutation(rec, field="required_top_level", value=()),
            dataclasses.replace(rec, api_keys_absent_subaccount_semantics="MAYBE"),
            dataclasses.replace(rec, subaccount_number_min=1),
            dataclasses.replace(rec, subaccount_number_max=62),
            dataclasses.replace(
                rec,
                restricted_key_error_signature=m.RestrictedKeyErrorSignature(
                    field_name="err", expected_value="restricted"
                ),
            ),
            dataclasses.replace(rec, signature_path_excludes_query=False),
            current_openapi_source(
                binding=current_openapi_binding(raw_source_sha256="a" * 64)
            ),
            current_openapi_source(
                binding=current_openapi_binding(raw_source_bytes=111)
            ),
            current_openapi_source(
                binding=current_openapi_binding(source_url="https://example.com/o.yaml")
            ),
            current_openapi_source(
                binding=current_openapi_binding(
                    historical_openapi_context_sha256="b" * 64
                )
            ),
            current_openapi_source(
                binding=current_openapi_binding(
                    observed_at_utc="2001-02-03T04:05:06Z"
                )
            ),
            dataclasses.replace(rec, record_label="OTHER_LABEL"),
        ]
        for i, mut in enumerate(mutations):
            assert changed_or_drift(mut), i
        # The pure provenance / label mutations must specifically change the hash.
        for mut in mutations[-6:]:
            assert mut.binding_record_sha256 != base_hash

    def test_n03_independent_recomputation(self):
        rec = current_openapi_source(record_label="RECOMPUTE_CHECK")
        indep = hashlib.sha256(
            _canon_json_bytes(_expected_canonical_binding_record(rec))
        ).hexdigest()
        result, _ = run_probe(
            full_discovery_script(api_keys=api_keys_body(include_subaccount_null=True)),
            source=rec,
        )
        assert json.loads(result.summary.to_json_bytes())["source_binding"][
            "record_sha256"
        ] == indep

    def test_n04_authoring_semantic_mismatch_drifts_pre_network(self):
        rec = dataclasses.replace(
            m.authoring_task_current_source_record(),
            api_keys_absent_subaccount_semantics="UNRESTRICTED",
        )
        assert (
            rec.evaluate_against_reviewed_contract().status
            == m.SourceEvaluationStatus.DRIFT
        )
        result, transport = run_probe(full_discovery_script(), source=rec)
        assert result.terminal_outcome == m.B1TerminalOutcome.B1_SOURCE_DRIFT
        assert result.manifest.request_count == 0 and transport.calls == []

    def test_n05_no_fabricated_empirical_timestamp(self):
        assert _FORBIDDEN_FABRICATED_TS not in Path(m.__file__).read_text(encoding="utf-8")
        assert _FORBIDDEN_FABRICATED_TS not in Path(__file__).read_text(encoding="utf-8")
        assert "SYNTHETIC" in "SYNTHETIC_TEST_ONLY_OBSERVED_AT"
        assert current_openapi_binding().observed_at_utc == SYNTHETIC_TEST_ONLY_OBSERVED_AT


class TestBIND08EvidenceSchemaAndCapabilityNonRegression:
    def test_manifest_and_summary_exact_key_sets_authoring_and_non_authoring(self):
        # not_exposed_source halts after /api_keys (2 requests); the
        # UNRESTRICTED current-source run completes all 4. The frozen key sets
        # must be identical either way (C08 / BIND-08).
        for src, expected_requests in (
            (not_exposed_source(), 2),
            (current_openapi_source(), 4),
        ):
            result, _ = run_probe(
                full_discovery_script(
                    api_keys=api_keys_body(include_subaccount_null=True)
                ),
                source=src,
            )
            manifest = json.loads(result.manifest.to_json_bytes())
            summary = json.loads(result.summary.to_json_bytes())
            assert manifest["schema_revision"] == 1
            assert summary["schema_revision"] == 1
            assert set(manifest) == _MANIFEST_KEYS
            assert set(summary) == _SUMMARY_KEYS
            assert set(summary["source_binding"]) == _SUMMARY_SOURCE_BINDING_KEYS
            assert manifest["request_count"] == expected_requests
            assert len(manifest["requests"]) == expected_requests
            for entry in manifest["requests"]:
                assert set(entry) == _MANIFEST_REQUEST_KEYS

    def test_c05_module_has_no_live_documentation_fetch(self):
        src_text = Path(m.__file__).read_text(encoding="utf-8")
        for banned in (
            "urllib.request",
            "urlopen",
            "http.client",
            "httpx",
            "aiohttp",
            "requests.get",
            "requests.request",
            "socket.create_connection",
            "socket.socket",
        ):
            assert banned not in src_text

    def test_c05_current_source_run_is_offline_and_injected(self):
        result, transport = run_probe(
            full_discovery_script(
                numbered=(), api_keys=api_keys_body(include_subaccount_null=True)
            ),
            source=current_openapi_source(),
        )
        assert transport.calls == [
            m.OP_ACCOUNT_LIMITS,
            m.OP_API_KEYS,
            m.OP_SUBACCOUNT_BALANCES,
            m.OP_SUBACCOUNT_NETTING,
        ]
        assert result.terminal_outcome == m.B1TerminalOutcome.B1_PRIMARY_ONLY_OBSERVED
        blob = result.summary.to_json_bytes() + result.manifest.to_json_bytes()
        assert b"docs.kalshi.com" not in blob  # source_url is not emitted

    def test_c07_unrestricted_route_still_reaches_reconciliation(self):
        for numbered, expected in (
            ((), m.B1TerminalOutcome.B1_PRIMARY_ONLY_OBSERVED),
            ((2, 5), m.B1TerminalOutcome.B1_EXISTING_NUMBERED_SUBACCOUNT_DISCOVERED),
        ):
            result, transport = run_probe(
                full_discovery_script(
                    numbered=numbered,
                    api_keys=api_keys_body(include_subaccount_null=True),
                ),
                source=current_openapi_source(semantics="UNRESTRICTED"),
            )
            assert transport.calls == [
                m.OP_ACCOUNT_LIMITS,
                m.OP_API_KEYS,
                m.OP_SUBACCOUNT_BALANCES,
                m.OP_SUBACCOUNT_NETTING,
            ], numbered
            assert result.terminal_outcome == expected, numbered
            summary = json.loads(result.summary.to_json_bytes())
            assert summary["current_key"]["restriction_state"] == "UNRESTRICTED"
            assert summary["enumeration"]["account_wide_enumeration_proven"] is True

    def test_c07_other_proof_predicates_not_weakened(self):
        r1, t1 = run_probe(
            {
                m.OP_ACCOUNT_LIMITS: resp(account_limits_body()),
                m.OP_API_KEYS: resp(api_keys_body(subaccount=3)),
            },
            source=current_openapi_source(),
        )
        assert r1.terminal_outcome == (
            m.B1TerminalOutcome.B1_ACCOUNT_WIDE_ENUMERATION_NOT_PROVEN_WITH_CURRENT_KEY
        )
        assert len(t1.calls) == 2
        r2, _ = run_probe(
            {
                m.OP_ACCOUNT_LIMITS: resp(account_limits_body()),
                m.OP_API_KEYS: resp(api_keys_body(include_subaccount_null=True)),
                m.OP_SUBACCOUNT_BALANCES: resp(balances_body([brow(2, balance="0")])),
                m.OP_SUBACCOUNT_NETTING: resp(netting_body([nrow(0), nrow(2)])),
            },
            source=current_openapi_source(),
        )
        assert r2.terminal_outcome == m.B1TerminalOutcome.B1_SOURCE_DRIFT

    def test_operational_boundary_constants_unchanged(self):
        assert m.MAX_REQUEST_COUNT == 4
        assert m.MAX_ATTEMPTS_PER_PATH == 1
        assert m.AUTOMATIC_RETRY_COUNT == 0
        assert m.MAX_REDIRECT_COUNT == 0
        assert m.PER_REQUEST_DEADLINE_MS == 10_000
        assert m.GLOBAL_EXECUTION_DEADLINE_MS == 40_000
        assert m.MAX_RESPONSE_BYTES_PER_REQUEST == 262_144
        assert m.MAX_TOTAL_RESPONSE_BYTES == 1_048_576
        assert m.DEMO_HOST == "external-api.demo.kalshi.co"
        assert m.DEMO_REST_BASE_URL == "https://external-api.demo.kalshi.co/trade-api/v2"
        assert m.ALLOWED_METHODS == frozenset({"GET"})
        assert m.ALLOWED_FULL_PATHS == frozenset(m.OP_FULL_PATHS.values())
        assert m.FORBIDDEN_PRIVATE_KEY_PEM_ENV == "KALSHI_DEMO_PRIVATE_KEY_PEM"
