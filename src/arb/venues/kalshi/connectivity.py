"""Kalshi Demo read-only connectivity preflight (Revision 03, Implementation 10).

Implements the bounded planning/execution boundary authorized by
`KALSHI_DEMO_READ_ONLY_CONNECTIVITY_PREFLIGHT_SPEC_03.md` and dispatched
by task `KALSHI_DEMO_READ_ONLY_CONNECTIVITY_PREFLIGHT_IMPLEMENTATION_10`,
a same-scope correction of Marco-blocked Implementation 09 (itself a
same-scope correction of Implementation 08, of Implementation 07, of
Implementation 06, of Implementation 05, of Implementation 04). This
candidate carries forward every accepted correction from those prior
review cycles; see the Implementation-04 through -10 Neo review handoffs
for the full history. This docstring describes the code as it stands
today, not as an implementation-04-only artifact.

Scope
-----

This module implements only:

* `plan_demo_read_only_connectivity(input)` -- pure, offline. Performs no
  DNS, socket, TLS, or HTTP activity.
* `execute_demo_read_only_connectivity(plan)` -- the one network-capable
  boundary. A real call is Kalshi Demo connectivity *execution* and
  requires its own separate Gustavo authorization; this implementation
  task authorizes only code and offline tests.

Neither function -- nor any internal type -- is re-exported from the
package top level (`arb.venues.kalshi`). Callers must
`import arb.venues.kalshi.connectivity` explicitly.

Revision 03, correction 1: Option-A deadline
----------------------------------------------

`CALLER_VISIBLE_EXECUTION_DEADLINE_MS = 10000`, measured from the first
instruction of `execute_demo_read_only_connectivity(plan)` to its return
-- including through response parsing and terminal result construction,
not just through the network I/O stages (Implementation 07 correction 1
closed a gap where a deadline exhausted during/after response parsing
could still have produced a success result).

DNS resolution is isolated in one private, least-privileged daemon
thread per call (never a reusable pool -- see `_resolve_addresses_with_deadline`),
and receives the full remaining overall budget, not the subordinate
socket-stage cap (Implementation 05 correction). The worker receives
only the exact hostname, port, and resolver call parameters; it has no
access to the plan, capability envelope, source binding, transport, or
any callback, and its only output channel is a private one-shot
`queue.Queue(maxsize=1)`. If the caller-visible deadline expires first,
the main thread stops waiting -- it does not join the worker, does not
wait for a thread-pool shutdown, and does not wait for any cancellation
acknowledgement -- and returns `CONNECTIVITY_TIMEOUT` with
`resolver_abandoned=True`, `request_count=0`, `retry_count=0`. The
underlying OS resolver call may finish afterward; if it does, its result
sits unread in the abandoned queue and is never consulted again, so it
cannot trigger TCP, TLS, HTTP, a callback, a retry, a fallback, or a
state-machine resumption. This is the accepted Option-A contract, not an
approximation of a stronger guarantee: Revision 03 explicitly does not
claim the underlying OS resolver operation itself terminates within
10 seconds.

Every post-DNS blocking operation -- TCP connect, TLS handshake, the
HTTP send, and every individual response `recv()` -- is bounded by
`min(5.0, positive_remaining_overall_s)`, recomputed immediately before
each blocking call (Implementation 06 correction). `deadline_ns`, the
sole overall-deadline anchor, is computed exactly once at function entry
and is never reset or reassigned.

Revision 03, correction 2: external authorization provenance
----------------------------------------------------------------

Runtime code performs exactly two things and claims exactly two things:

* `CAPABILITY_STRUCTURE_VALIDATED` -- structural/current-value validation
  of `TaskAuthorizationCapabilityEnvelope` via the unmodified, reused
  `require_usable_capability_envelope(...)`.
* `SOURCE_RECORD_AND_HASH_CONSISTENT` -- independent hashing, canonical-
  byte validation, closed-schema parsing, and internal reconciliation of
  `source_binding_record_bytes` against the two hashes carried on a new,
  connectivity-local, immutable `ExecutionDispatchExpectation`.

Establishing `AUTHORIZATION_PROVENANCE_EXTERNAL` -- that a given
`TaskAuthorizationCapabilityEnvelope` and `ExecutionDispatchExpectation`
actually originated from the current Gustavo execution dispatch -- is
the responsibility of the orchestration layer that constructs
`ConnectivityPreflightInput` in the first place, not of this module. This
module never claims `GUSTAVO_SIGNATURE_VERIFIED`,
`GUSTAVO_PROVENANCE_CRYPTOGRAPHICALLY_VERIFIED`, or
`AUTHORIZATION_PROVENANCE_VERIFIED_BY_HASH` anywhere -- not in a halt
code, not in success evidence, not in a docstring, and not in a log
line. `ConnectivityPreflightSuccess.authorization_provenance_mode` is
always `ExecutionProvenanceMode.EXTERNAL_GUSTAVO_ORCHESTRATION` and
`runtime_authorization_provenance_proof` is always
`RuntimeProvenanceProof.NOT_PERFORMED_BY_DESIGN` -- constants, not
computed claims. No HMAC, signature, key, certificate, credential, nonce,
or other in-process trust root is introduced anywhere in this module.
`TaskAuthorizationCapabilityEnvelope` and `models.py` are unmodified by
this task.

Every current-value gate -- `ValidatedDemoProfile` (Implementation 06
correction) and `OfficialRestSourceBinding` (Implementation 07/08
corrections) -- requires the *exact* canonical model/connectivity-local
type for every nested field before any value comparison runs, so a
duck-typed or proxy object exposing a deceptive `.value` or overridden
equality cannot impersonate a real enum member or dataclass instance.

`OfficialRestSourceBinding` revalidation no longer relies on a redundant
mutable copy of any one field as a purported commitment (the
Implementation-07 approach, which Marco correctly rejected as
insufficient). Instead, `ConnectivityPreflightPlan` retains the exact
canonical `source_binding_record_bytes` the binding was derived from as
connectivity-local immutable plan state -- the caller's own original
bytes, not a secret or new trust root -- and
`require_usable_official_rest_source_binding` mechanically rehashes
those bytes against the current `ExecutionDispatchExpectation`,
re-parses and revalidates them under the accepted canonical schema, and
recomputes every authoritative field value from scratch via the single
shared `_derive_official_rest_source_binding_fields` function (used both
when the binding is first built during planning and every later time it
is revalidated at a use-time consumption gate), comparing each of
`binding`'s current fields -- by exact type and value -- against its
freshly recomputed counterpart (Implementation 08 correction 1).

The accepted source-binding `retrieved_at_utc` timestamp is validated
against an exact-syntax, ASCII-only RFC 3339 UTC grammar (Implementation
08 correction 2, hardened by Implementation 09 correction 2 to use the
literal `[0-9]` character class instead of Unicode-aware `\\d` and
`re.fullmatch(...)` instead of `^...$`-anchored `.match(...)`, closing a
Unicode-digit-smuggling gap and a trailing-newline gap respectively), not
the much more permissive grammar `datetime.fromisoformat()` alone
accepts -- see `_is_rfc3339_utc`.

When an OpenAPI record's operation and root objects both omit `security`
entirely (`effective_security_source = NONE_DECLARED`,
`effective_security = null`), the accepted specification (Section 5.5.2)
states this means no security requirement is declared at all --
Implementation 09 correction 1 fixes `_classify_effective_security` to
recognize this as an affirmatively public state
(`PUBLIC_UNAUTHENTICATED_READ_ONLY`), correcting Implementation 08 and
earlier's misclassification of it as `UNKNOWN_OR_CONFLICTING`.

Once the single HTTP send attempt has begun, an I/O error from
`sendall()` cannot prove zero bytes were transmitted, so it is treated
as `REQUEST_RESULT_UNKNOWN` rather than `TRANSPORT_FAILURE`
(Implementation 07 correction 3) -- consistent with the existing
Section 14.3 rule that any interruption after the send attempt starts
and before terminal response classification is `REQUEST_RESULT_UNKNOWN`,
never an automatic resend.

Implementation 10 closes four further findings. `_is_sha256_hex` now
requires an exact ASCII `[0-9a-f]{64}` lexeme via `re.fullmatch(...)`
rather than `int(value, 16)` (which, like the RFC 3339 validator before
its own Implementation-09 fix, silently accepts Unicode decimal-digit
characters standing in for ASCII `0`-`9`) -- applied to
`ExecutionDispatchExpectation`'s two expected-hash fields, the source
record's own `raw_openapi_sha256`, and every current
`OfficialRestSourceBinding` hash field. `_resolve_addresses` no longer
discards the address `family` `socket.getaddrinfo()` actually returns;
`_classify_dns_answer` now cross-validates that family against the
parsed IP version and the `sockaddr` shape for every candidate before
any address is canonicalized, deduplicated, or sorted -- an unknown
family, a family/address-version mismatch, or a malformed `sockaddr`
each reject the entire DNS answer, exactly like a prohibited address
already did. `require_usable_validated_demo_profile` now also validates
`profile.websocket` (exact type and every field) and
`allowlist_revision`/`validation_schema_revision` (hard-bound to
`"candidate-02"`/`1`, the only values exercised by every pre-existing
canonical test fixture in this repository) -- none of this module ever
connects a WebSocket, but a mutated or duck-typed `profile.websocket`
was not previously grounds for rejection. `_is_lowercase_media_type`
now treats any whitespace-only string as blank (the same
`value.strip() == ""` rule `models.py` uses internally), not just the
empty string.
"""

from __future__ import annotations

import enum
import hashlib
import ipaddress
import json
import queue
import re
import socket
import ssl
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import FrozenSet, Optional, Tuple

from .models import (
    CredentialReferenceKind,
    CredentialReferenceState,
    EndpointComponents,
    Environment,
    RequestedCapability,
    TaskAuthorizationCapabilityEnvelope,
    ValidatedDemoProfile,
    require_usable_capability_envelope,
)

__all__ = [
    "ConnectivityStage",
    "RestAuthenticationClass",
    "EffectiveSecuritySource",
    "ExecutionProvenanceMode",
    "RuntimeProvenanceProof",
    "ConnectivityHaltCode",
    "DEMO_HOST",
    "DEMO_PORT",
    "DEMO_BASE_PATH",
    "DEMO_ROUTE",
    "DEMO_FULL_PATH",
    "PRODUCTION_REST_HOSTS",
    "DEMO_COMPATIBILITY_HOST",
    "ExecutionDispatchExpectation",
    "ConnectivityPreflightInput",
    "ConnectivityPreflightPlan",
    "ConnectivityPreflightSuccess",
    "ConnectivityPreflightHalt",
    "ConnectivityError",
    "ConnectivityTypeError",
    "require_usable_validated_demo_profile",
    "require_usable_execution_dispatch_expectation",
    "require_usable_connectivity_preflight_plan",
    "plan_demo_read_only_connectivity",
    "execute_demo_read_only_connectivity",
]
# Deliberately NOT exported: `OfficialRestSourceBinding`, `VerifiedDnsSet`,
# `require_usable_official_rest_source_binding`,
# `require_usable_verified_dns_set` -- internal derived-result types and
# their gates, reachable only by qualified attribute access for tests.
#
# `src/arb/venues/kalshi/__init__.py` is NOT modified by this
# implementation. None of the names above -- including
# `execute_demo_read_only_connectivity` -- are reachable through
# `arb.venues.kalshi` top-level imports.

_MISSING = object()

# ---------------------------------------------------------------------------
# Exact Demo origin and operation identities.
# ---------------------------------------------------------------------------

DEMO_HOST = "external-api.demo.kalshi.co"
DEMO_PORT = 443
DEMO_ORIGIN = "https://external-api.demo.kalshi.co"
DEMO_BASE_PATH = "/trade-api/v2"
DEMO_ROUTE = "/exchange/status"
DEMO_FULL_PATH = "/trade-api/v2/exchange/status"

# Implementation 10 correction 3: the profile's WebSocket endpoint is
# never connected by this module, but require_usable_validated_demo_profile
# now validates it anyway, matching the exact values the unmodified
# validation.py's `_DEMO_WEBSOCKET` constant produces.
DEMO_WEBSOCKET_HOST = "external-api-ws.demo.kalshi.co"
DEMO_WEBSOCKET_PATH = "/trade-api/ws/v2"

PRODUCTION_REST_HOSTS: FrozenSet[str] = frozenset(
    {"external-api.kalshi.com", "api.elections.kalshi.com"}
)
DEMO_COMPATIBILITY_HOST = "demo-api.kalshi.co"

_EXPECTED_SOURCE_URL = "https://docs.kalshi.com/openapi.yaml"
_EXPECTED_OPERATION_METHOD = "GET"
_EXPECTED_OPERATION_PATH = "/exchange/status"
_EXPECTED_BINDING_SCHEMA_REVISION = 1

# Verified against every pre-existing canonical test fixture in this
# repository (none of which is writable by this task) -- see the
# comment in require_usable_validated_demo_profile.
_ACCEPTED_ALLOWLIST_REVISION = "candidate-02"
_ACCEPTED_VALIDATION_SCHEMA_REVISION = 1

_MAX_RESPONSE_BYTES = 65536
_OVERALL_TIMEOUT_MS = 10000
_SOCKET_STAGE_TIMEOUT_MS = 5000
_REQUEST_BUDGET = 1


# ---------------------------------------------------------------------------
# Section 8.1 -- closed enums.
# ---------------------------------------------------------------------------


class ConnectivityStage(enum.StrEnum):
    PLAN_INPUT = "PLAN_INPUT"
    CAPABILITY_ENVELOPE_VALIDATED = "CAPABILITY_ENVELOPE_VALIDATED"
    EXECUTION_DISPATCH_EXPECTATION_VALIDATED = "EXECUTION_DISPATCH_EXPECTATION_VALIDATED"
    PROFILE_VERIFIED = "PROFILE_VERIFIED"
    SOURCE_RECORD_IDENTITY_VERIFIED = "SOURCE_RECORD_IDENTITY_VERIFIED"
    SOURCE_BOUND = "SOURCE_BOUND"
    PRE_DNS_CURRENT_VALUES_REVERIFIED = "PRE_DNS_CURRENT_VALUES_REVERIFIED"
    DNS_RESOLUTION_WAIT = "DNS_RESOLUTION_WAIT"
    DNS_RESOLVED = "DNS_RESOLVED"
    DNS_SET_VERIFIED = "DNS_SET_VERIFIED"
    PRE_SOCKET_CURRENT_VALUES_REVERIFIED = "PRE_SOCKET_CURRENT_VALUES_REVERIFIED"
    TCP_CONNECTED_TO_PINNED_ADDRESS = "TCP_CONNECTED_TO_PINNED_ADDRESS"
    TLS_VERIFIED_FOR_DEMO_HOSTNAME = "TLS_VERIFIED_FOR_DEMO_HOSTNAME"
    PRE_SEND_CURRENT_VALUES_REVERIFIED = "PRE_SEND_CURRENT_VALUES_REVERIFIED"
    REQUEST_SENT = "REQUEST_SENT"
    RESPONSE_HEADERS_RECEIVED = "RESPONSE_HEADERS_RECEIVED"
    RESPONSE_VALIDATED = "RESPONSE_VALIDATED"
    SUCCEEDED = "SUCCEEDED"
    HALTED = "HALTED"


class RestAuthenticationClass(enum.StrEnum):
    PUBLIC_UNAUTHENTICATED_READ_ONLY = "PUBLIC_UNAUTHENTICATED_READ_ONLY"
    AUTHENTICATED_READ_ONLY = "AUTHENTICATED_READ_ONLY"
    UNKNOWN_OR_CONFLICTING = "UNKNOWN_OR_CONFLICTING"


class EffectiveSecuritySource(enum.StrEnum):
    OPERATION_OVERRIDE = "OPERATION_OVERRIDE"
    GLOBAL_INHERITED = "GLOBAL_INHERITED"
    NONE_DECLARED = "NONE_DECLARED"


class ExecutionProvenanceMode(enum.StrEnum):
    """Section 8.1. Exactly one member for Revision 03."""

    EXTERNAL_GUSTAVO_ORCHESTRATION = "EXTERNAL_GUSTAVO_ORCHESTRATION"


class RuntimeProvenanceProof(enum.StrEnum):
    """Section 8.1. Exactly one member for Revision 03. Runtime code
    never claims a stronger value than this."""

    NOT_PERFORMED_BY_DESIGN = "NOT_PERFORMED_BY_DESIGN"


class ConnectivityHaltCode(enum.StrEnum):
    ENVIRONMENT_UNSET = "ENVIRONMENT_UNSET"
    ENVIRONMENT_UNKNOWN = "ENVIRONMENT_UNKNOWN"
    ENVIRONMENT_NOT_AUTHORIZED = "ENVIRONMENT_NOT_AUTHORIZED"
    PRODUCTION_ACCESS_PROHIBITED = "PRODUCTION_ACCESS_PROHIBITED"
    ENVIRONMENT_ENDPOINT_MISMATCH = "ENVIRONMENT_ENDPOINT_MISMATCH"
    ENDPOINT_NOT_ALLOWLISTED = "ENDPOINT_NOT_ALLOWLISTED"
    ENDPOINT_REDIRECT_PROHIBITED = "ENDPOINT_REDIRECT_PROHIBITED"
    CAPABILITY_NOT_AUTHORIZED = "CAPABILITY_NOT_AUTHORIZED"
    OFFICIAL_SOURCE_CONFLICT = "OFFICIAL_SOURCE_CONFLICT"

    OFFICIAL_SOURCE_IDENTITY_UNBOUND = "OFFICIAL_SOURCE_IDENTITY_UNBOUND"
    EXECUTION_CAPABILITY_NOT_AUTHORIZED = "EXECUTION_CAPABILITY_NOT_AUTHORIZED"
    EXECUTION_INPUT_TYPE_INVALID = "EXECUTION_INPUT_TYPE_INVALID"
    EXECUTION_PLAN_MUTATED = "EXECUTION_PLAN_MUTATED"
    DNS_VERIFICATION_FAILED = "DNS_VERIFICATION_FAILED"
    TLS_VERIFICATION_FAILED = "TLS_VERIFICATION_FAILED"
    CONNECTIVITY_TIMEOUT = "CONNECTIVITY_TIMEOUT"
    REQUEST_BUDGET_EXHAUSTED = "REQUEST_BUDGET_EXHAUSTED"
    UNEXPECTED_AUTHENTICATION_REQUIREMENT = "UNEXPECTED_AUTHENTICATION_REQUIREMENT"
    UNEXPECTED_HTTP_STATUS = "UNEXPECTED_HTTP_STATUS"
    RESPONSE_MALFORMED = "RESPONSE_MALFORMED"
    TRANSPORT_FAILURE = "TRANSPORT_FAILURE"
    REQUEST_RESULT_UNKNOWN = "REQUEST_RESULT_UNKNOWN"


class ConnectivityError(ValueError):
    """Base for this module's own typed validation failures."""


class ConnectivityTypeError(ConnectivityError):
    """Raised when a consumption boundary observes the wrong exact
    runtime type."""


class _SourceIdentityUnboundError(ConnectivityError):
    """Missing/placeholder/fabricated/stale/mismatched/noncanonical
    source-binding identity -- maps to `OFFICIAL_SOURCE_IDENTITY_UNBOUND`.
    Per Section 12.2, this never means Python proved or disproved
    Gustavo provenance -- only that structural/hash consistency failed."""


class _SourceConflictError(ConnectivityError):
    """Structurally bound record whose security facts conflict with the
    public-read specification -- maps to `OFFICIAL_SOURCE_CONFLICT`."""


# ---------------------------------------------------------------------------
# Section 7.6/7.7 -- success and halt records.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, repr=False, eq=True)
class ConnectivityPreflightHalt:
    code: ConnectivityHaltCode
    stage: ConnectivityStage
    expected: Optional[str] = None
    observed: Optional[str] = None
    request_count: int = 0
    retry_count: int = 0
    caller_visible_elapsed_ms: int = 0
    resolver_abandoned: bool = False
    authorization_provenance_mode: ExecutionProvenanceMode = (
        ExecutionProvenanceMode.EXTERNAL_GUSTAVO_ORCHESTRATION
    )
    runtime_authorization_provenance_proof: RuntimeProvenanceProof = (
        RuntimeProvenanceProof.NOT_PERFORMED_BY_DESIGN
    )

    def __repr__(self) -> str:  # pragma: no cover - trivial
        parts = [f"code={self.code.value}", f"stage={self.stage.value}"]
        if self.expected is not None:
            parts.append(f"expected={self.expected}")
        if self.observed is not None:
            parts.append(f"observed={self.observed}")
        parts.append(f"request_count={self.request_count}")
        parts.append(f"retry_count={self.retry_count}")
        parts.append(f"caller_visible_elapsed_ms={self.caller_visible_elapsed_ms}")
        parts.append(f"resolver_abandoned={self.resolver_abandoned}")
        return "ConnectivityPreflightHalt(" + ", ".join(parts) + ")"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.__repr__()


def _halt(
    code: ConnectivityHaltCode,
    stage: ConnectivityStage,
    *,
    expected: Optional[str] = None,
    observed: Optional[str] = None,
    request_count: int = 0,
    retry_count: int = 0,
    caller_visible_elapsed_ms: int = 0,
    resolver_abandoned: bool = False,
) -> ConnectivityPreflightHalt:
    return ConnectivityPreflightHalt(
        code=code,
        stage=stage,
        expected=expected,
        observed=observed,
        request_count=request_count,
        retry_count=retry_count,
        caller_visible_elapsed_ms=caller_visible_elapsed_ms,
        resolver_abandoned=resolver_abandoned,
    )


# ---------------------------------------------------------------------------
# require_usable_validated_demo_profile (Section 7.3).
# ---------------------------------------------------------------------------


def require_usable_validated_demo_profile(profile: object) -> None:
    """Section 7.3, hardened per the Implementation-06 finding: every
    nested field is checked for its *exact* canonical model type before
    any value/identity check runs on it, so a duck-typed or proxy object
    that merely exposes a matching `.value` (or otherwise deceptive
    equality) attribute cannot pass by impersonating the real type."""

    if type(profile) is not ValidatedDemoProfile:
        raise ConnectivityTypeError(
            "profile must have exact type ValidatedDemoProfile"
        )

    if type(profile.environment) is not Environment:
        raise ConnectivityTypeError(
            "profile.environment must have exact type Environment"
        )
    if profile.environment is not Environment.KALSHI_DEMO:
        raise ConnectivityError("profile.environment must be KALSHI_DEMO")

    if type(profile.requested_capability) is not RequestedCapability:
        raise ConnectivityTypeError(
            "profile.requested_capability must have exact type RequestedCapability"
        )
    if profile.requested_capability is not RequestedCapability.DEMO_PUBLIC_REST_READ:
        raise ConnectivityError(
            "profile.requested_capability must be DEMO_PUBLIC_REST_READ"
        )

    if type(profile.effective_capability) is not RequestedCapability:
        raise ConnectivityTypeError(
            "profile.effective_capability must have exact type RequestedCapability"
        )
    if profile.effective_capability is not RequestedCapability.DEMO_PUBLIC_REST_READ:
        raise ConnectivityError(
            "profile.effective_capability must be DEMO_PUBLIC_REST_READ"
        )

    if type(profile.rest) is not EndpointComponents:
        raise ConnectivityTypeError(
            "profile.rest must have exact type EndpointComponents"
        )
    if not _is_exact_str(profile.rest.scheme) or profile.rest.scheme != "https":
        raise ConnectivityError("profile.rest.scheme must be the exact built-in str 'https'")
    if not _is_exact_str(profile.rest.host) or profile.rest.host != DEMO_HOST:
        raise ConnectivityError("profile.rest must target the exact built-in str Demo host")
    if not _is_exact_int(profile.rest.port) or profile.rest.port != DEMO_PORT:
        raise ConnectivityError("profile.rest port must be the exact built-in int 443")
    if not _is_exact_str(profile.rest.path) or profile.rest.path != DEMO_BASE_PATH:
        raise ConnectivityError(
            "profile.rest path must be the exact built-in str Demo base path"
        )
    if not _is_exact_bool(profile.rest.has_user_info) or profile.rest.has_user_info is not False:
        raise ConnectivityError("profile.rest.has_user_info must be the exact bool False")
    if not _is_exact_bool(profile.rest.has_query) or profile.rest.has_query is not False:
        raise ConnectivityError("profile.rest.has_query must be the exact bool False")
    if not _is_exact_bool(profile.rest.has_fragment) or profile.rest.has_fragment is not False:
        raise ConnectivityError("profile.rest.has_fragment must be the exact bool False")

    # Implementation 10 correction 3: complete current-value validation
    # of profile.websocket (previously not checked at all -- this
    # module never connects a WebSocket, but a mutated/duck-typed
    # profile.websocket was not previously grounds for rejection) and
    # of allowlist_revision/validation_schema_revision. The exact
    # values below were verified against every pre-existing canonical
    # test fixture in this repository (test_kalshi_capability_envelope.py,
    # test_kalshi_credential_metadata.py, test_kalshi_endpoint_validation.py,
    # test_kalshi_environment_validation.py, test_kalshi_network_denial.py,
    # test_kalshi_secret_safety.py) -- every one of them supplies
    # config_schema_revision=1 and endpoint_allowlist_revision=
    # "candidate-02" to the unmodified validate() function, and
    # validation.py passes both straight through
    # (validation_schema_revision=config.config_schema_revision,
    # allowlist_revision=endpoint_profile.allowlist_revision) with no
    # other accepted value exercised anywhere in this codebase. No
    # unexplained canonical mismatch was found.
    if type(profile.websocket) is not EndpointComponents:
        raise ConnectivityTypeError(
            "profile.websocket must have exact type EndpointComponents"
        )
    if not _is_exact_str(profile.websocket.scheme) or profile.websocket.scheme != "wss":
        raise ConnectivityError(
            "profile.websocket.scheme must be the exact built-in str 'wss'"
        )
    if (
        not _is_exact_str(profile.websocket.host)
        or profile.websocket.host != DEMO_WEBSOCKET_HOST
    ):
        raise ConnectivityError(
            "profile.websocket.host must be the exact built-in str Demo WebSocket host"
        )
    if not _is_exact_int(profile.websocket.port) or profile.websocket.port != DEMO_PORT:
        raise ConnectivityError("profile.websocket.port must be the exact built-in int 443")
    if (
        not _is_exact_str(profile.websocket.path)
        or profile.websocket.path != DEMO_WEBSOCKET_PATH
    ):
        raise ConnectivityError(
            "profile.websocket.path must be the exact built-in str Demo WebSocket path"
        )
    if (
        not _is_exact_bool(profile.websocket.has_user_info)
        or profile.websocket.has_user_info is not False
    ):
        raise ConnectivityError("profile.websocket.has_user_info must be the exact bool False")
    if (
        not _is_exact_bool(profile.websocket.has_query)
        or profile.websocket.has_query is not False
    ):
        raise ConnectivityError("profile.websocket.has_query must be the exact bool False")
    if (
        not _is_exact_bool(profile.websocket.has_fragment)
        or profile.websocket.has_fragment is not False
    ):
        raise ConnectivityError("profile.websocket.has_fragment must be the exact bool False")

    if (
        not _is_exact_str(profile.allowlist_revision)
        or profile.allowlist_revision != _ACCEPTED_ALLOWLIST_REVISION
    ):
        raise ConnectivityError(
            "profile.allowlist_revision must be the exact accepted built-in str "
            f"{_ACCEPTED_ALLOWLIST_REVISION!r}"
        )
    if (
        not _is_exact_int(profile.validation_schema_revision)
        or profile.validation_schema_revision != _ACCEPTED_VALIDATION_SCHEMA_REVISION
    ):
        raise ConnectivityError(
            "profile.validation_schema_revision must be the exact accepted "
            f"built-in int {_ACCEPTED_VALIDATION_SCHEMA_REVISION!r}"
        )

    if type(profile.credential_reference_states) is not tuple:
        raise ConnectivityTypeError(
            "profile.credential_reference_states must have exact type tuple"
        )
    for entry in profile.credential_reference_states:
        if type(entry) is not tuple or len(entry) != 2:
            raise ConnectivityTypeError(
                "each profile.credential_reference_states entry must be an "
                "exact 2-tuple"
            )
        kind, state = entry
        if type(kind) is not CredentialReferenceKind:
            raise ConnectivityTypeError(
                "each credential reference kind must have exact type "
                "CredentialReferenceKind"
            )
        if type(state) is not CredentialReferenceState:
            raise ConnectivityTypeError(
                "each credential reference state must have exact type "
                "CredentialReferenceState"
            )
        if state is not CredentialReferenceState.NOT_REQUIRED:
            raise ConnectivityError(
                "profile.credential_reference_states must be empty or NOT_REQUIRED"
            )

    if not _is_exact_bool(profile.secret_loaded) or profile.secret_loaded is not False:
        raise ConnectivityError("profile.secret_loaded must be the exact bool False")
    if (
        not _is_exact_bool(profile.transport_constructed)
        or profile.transport_constructed is not False
    ):
        raise ConnectivityError("profile.transport_constructed must be the exact bool False")
    if (
        not _is_exact_bool(profile.network_request_sent)
        or profile.network_request_sent is not False
    ):
        raise ConnectivityError("profile.network_request_sent must be the exact bool False")


# ---------------------------------------------------------------------------
# Section 7.1/7.5 -- `ExecutionDispatchExpectation` (Revision 03).
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExecutionDispatchExpectation:
    """Section 7.1. Carries exactly the two dispatch-bound expected
    identity hashes plus the closed provenance-mode label. No signature,
    key, HMAC, credential, bearer token, certificate, nonce, or secret is
    present -- and none may be added to this type."""

    expected_source_binding_record_sha256: str
    expected_raw_openapi_sha256: str
    provenance_mode: ExecutionProvenanceMode


_SHA256_HEX_PATTERN = re.compile(r"[0-9a-f]{64}")


def _is_sha256_hex(value: object) -> bool:
    """Implementation 10 correction 1: exact ASCII SHA-256 lexeme
    validator. Uses a literal ASCII character class plus
    `re.fullmatch(...)` -- the same pattern used to fix `_is_rfc3339_utc`
    in Implementation 09 -- rather than `int(value, 16)`. `int(x, 16)`
    is not a safe lexical validator here: Python's `int()` constructor
    accepts many Unicode decimal-digit characters standing in for
    ASCII `0`-`9` (for example, Arabic-Indic or full-width digits), so
    a hash string containing those would silently parse as if it were
    plain ASCII hex, even though it is byte-for-byte different from
    what it visually resembles. `re.fullmatch(r"[0-9a-f]{64}", value)`
    only matches the 16 literal ASCII characters `0-9a-f`; uppercase
    ASCII hex, Unicode digit lookalikes, and any other character are
    all rejected structurally, and `fullmatch` (as opposed to `match`
    with `^`/`$` anchors) requires the entire string to be consumed, so
    a trailing character (including a trailing newline) is also
    rejected. This is used for every SHA-256 string this component
    consumes: `ExecutionDispatchExpectation`'s two expected-hash
    fields, the source record's own `raw_openapi_sha256`, and every
    current `OfficialRestSourceBinding` hash field."""

    if type(value) is not str:
        return False
    if _SHA256_HEX_PATTERN.fullmatch(value) is None:
        return False
    if value == "0" * 64:
        return False
    return True


def require_usable_execution_dispatch_expectation(expectation: object) -> None:
    """Section 7.5, items 1-3. Exact type, exact field set (guaranteed
    by the frozen dataclass), non-placeholder hash syntax, and the
    single closed provenance mode. This function proves nothing about
    *where* the expectation came from -- see the module docstring."""

    if type(expectation) is not ExecutionDispatchExpectation:
        raise ConnectivityTypeError(
            "execution dispatch expectation must have exact type "
            "ExecutionDispatchExpectation"
        )
    if expectation.provenance_mode is not ExecutionProvenanceMode.EXTERNAL_GUSTAVO_ORCHESTRATION:
        raise ConnectivityError(
            "execution dispatch expectation provenance_mode must be "
            "EXTERNAL_GUSTAVO_ORCHESTRATION"
        )
    if not _is_sha256_hex(expectation.expected_source_binding_record_sha256):
        raise _SourceIdentityUnboundError(
            "expected_source_binding_record_sha256 is malformed, blank, or placeholder"
        )
    if not _is_sha256_hex(expectation.expected_raw_openapi_sha256):
        raise _SourceIdentityUnboundError(
            "expected_raw_openapi_sha256 is malformed, blank, or placeholder"
        )


# ---------------------------------------------------------------------------
# Section 7.5 -- canonical source-binding record parsing and
# `OfficialRestSourceBinding`.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OfficialRestSourceBinding:
    """Internal derived result. Never accepted as a caller-created
    object at a planning or execution boundary.

    Implementation 08 removes the Implementation-07 redundant
    "commitment" field: a second mutable copy of one field is not a
    real binding back to the canonical record (Marco correctly rejected
    it as "another redundant mutable copy of a field as a purported
    commitment"). Instead, every field on this object is revalidated at
    every use-time consumption gate by rehashing and re-parsing the
    actual retained canonical record bytes and recomputing the
    authoritative value of every field from scratch -- see
    `_derive_official_rest_source_binding_fields` and
    `require_usable_official_rest_source_binding`."""

    source_url: str
    retrieved_at_utc: str
    raw_openapi_byte_length: int
    raw_openapi_sha256: str
    source_binding_record_byte_length: int
    source_binding_record_sha256: str
    operation_method: str
    operation_path: str
    effective_security_source: EffectiveSecuritySource
    effective_auth_classification: RestAuthenticationClass
    reviewed_demo_rest_origin: str
    reviewed_full_request_path: str
    binding_schema_revision: int


_SOURCE_BINDING_RECORD_FIELDS = frozenset(
    {
        "schema_version",
        "source_url",
        "retrieved_at_utc",
        "http_status",
        "normalized_source_media_type",
        "raw_openapi_byte_length",
        "raw_openapi_sha256",
        "operation_method",
        "operation_path",
        "global_security_key_present",
        "operation_security_key_present",
        "effective_security_source",
        "effective_security",
        "effective_allows_anonymous",
        "effective_auth_classification",
        "reviewed_demo_rest_origin",
        "reviewed_full_request_path",
        "binding_schema_revision",
    }
)


def _reject_duplicate_keys(pairs):
    seen = set()
    result = {}
    for key, value in pairs:
        if key in seen:
            raise ConnectivityError(f"duplicate source-binding-record key: {key}")
        seen.add(key)
        result[key] = value
    return result


def _reject_json_constant(token: str):
    raise ConnectivityError(f"non-finite JSON constant is prohibited: {token}")


def _is_exact_int(value: object) -> bool:
    return type(value) is int  # excludes bool (type(True) is bool, not int)


def _is_exact_bool(value: object) -> bool:
    return type(value) is bool


def _is_exact_str(value: object) -> bool:
    """`type(x) is str` rather than `isinstance`/`==` alone: a `str`
    subclass can hold a different actual value while overriding
    `__eq__`/`__hash__` to falsely claim equality with an expected
    constant. `type()` identity bypasses any such override entirely,
    so this check cannot be fooled by a str-subclass whose real content
    is a prohibited hostname/path/method."""

    return type(value) is str


def _is_lowercase_media_type(value: object) -> bool:
    """Implementation 10 correction 4: exact type, then the same
    deterministic blank rule as `models.py`'s `_is_blank_string`
    (`value.strip() == ""`) -- which correctly treats whitespace-only
    strings (a single space, multiple spaces, a tab, a CRLF pair, and
    so on) as blank, not just the empty string `""`. The previous
    `not value` check only caught the empty string; any nonempty
    whitespace-only string passed it. Reused here rather than imported,
    since `_is_blank_string` is `models.py`-private and this task may
    not modify `models.py`."""

    if type(value) is not str:
        return False
    if value.strip() == "":
        return False
    return value == value.lower()


_RFC3339_UTC_STRICT_PATTERN = re.compile(
    r"([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})"
    r"(?:\.([0-9]+))?(Z|\+00:00)"
)


def _is_rfc3339_utc(value: object) -> bool:
    """Implementation 08 correction 2, hardened by Implementation 09
    correction 2: exact-syntax RFC 3339 UTC timestamp validator,
    deliberately stricter than the `datetime.fromisoformat()`-only rule
    it originally replaced. This validator requires, in order: an exact
    built-in `str`; the extended calendar date form `YYYY-MM-DD`; a
    literal uppercase `T`; `HH:MM:SS`; an optional RFC3339-conforming
    fractional-seconds suffix; and exactly one of the literal
    designators `Z` or `+00:00` (no other UTC spelling, and no non-UTC
    offset of any kind). Syntactically well-formed but calendrically
    impossible values (for example, `2026-02-30T00:00:00Z`) are still
    rejected by constructing a real `datetime` from the captured
    fields.

    Two properties, both required by Implementation 09 correction 2,
    are easy to get wrong with a naive regex and are handled explicitly
    here:

    * Every digit class in the pattern uses the literal ASCII character
      class `[0-9]`, never the shorthand `\\d`. Without `re.ASCII`,
      Python's `\\d` matches *any* Unicode character with the decimal-
      digit property -- full-width digits (e.g. U+FF10-U+FF19),
      Arabic-Indic digits (U+0660-U+0669), and others -- and
      `int()` on the resulting string would happily parse those too, so
      a `\\d`-based pattern would silently accept a visually-similar but
      byte-for-byte different timestamp. `[0-9]` matches only the
      literal ASCII digit characters.
    * `re.fullmatch(...)` is used instead of `re.match(...)` with `^`/`$`
      anchors. Python's `$` matches either at the absolute end of the
      string *or* immediately before a single trailing `\\n` -- so a
      `^...$`-anchored pattern would incorrectly accept
      `"2026-08-07T00:00:00Z\\n"`. `fullmatch` requires the entire
      string to be consumed with no trailing characters of any kind.

    This is the single validator used both when a source-binding record
    is first produced/consumed (`_derive_official_rest_source_binding_fields`,
    called once during planning) and every later time it is revalidated
    at a use-time consumption gate (the same function, called again at
    each gate) -- so the syntax rule cannot drift between the two."""

    if type(value) is not str:
        return False
    match = _RFC3339_UTC_STRICT_PATTERN.fullmatch(value)
    if match is None:
        return False
    year, month, day, hour, minute, second, _fraction, _designator = match.groups()
    try:
        datetime(int(year), int(month), int(day), int(hour), int(minute), int(second))
    except ValueError:
        return False
    return True


def _canonical_record_bytes(record: dict) -> bytes:
    """The exact Section-5.5.3-derived canonical serialization
    (unchanged from Revision 02/Implementation 03)."""

    return json.dumps(
        record,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _validate_security_requirement_objects(security: object) -> None:
    if not isinstance(security, list):
        raise _SourceConflictError("effective_security must be a JSON array")
    for requirement in security:
        if not isinstance(requirement, dict):
            raise _SourceConflictError(
                "effective_security entries must be Security Requirement Objects"
            )
        for scheme_name, scopes in requirement.items():
            if type(scheme_name) is not str:
                raise _SourceConflictError(
                    "Security Requirement Object keys must be strings"
                )
            if not isinstance(scopes, list) or not all(
                type(scope) is str for scope in scopes
            ):
                raise _SourceConflictError(
                    "Security Requirement Object scope lists must be string arrays"
                )


def _classify_effective_security(
    source: EffectiveSecuritySource, security: object
) -> Tuple[bool, RestAuthenticationClass]:
    """Section 5.5.2. Implementation 09 correction 1: when neither the
    operation nor the root OpenAPI object declares `security`
    (`NONE_DECLARED`, with `effective_security` null), the accepted
    specification states this means *no security requirement is
    declared* -- which is a valid, affirmatively public state, not an
    ambiguous or conflicting one. Implementation 08 and earlier
    incorrectly classified this as `UNKNOWN_OR_CONFLICTING`."""

    if source is EffectiveSecuritySource.NONE_DECLARED:
        if security is not None:
            raise _SourceConflictError(
                "NONE_DECLARED effective_security_source requires null security"
            )
        return True, RestAuthenticationClass.PUBLIC_UNAUTHENTICATED_READ_ONLY

    _validate_security_requirement_objects(security)

    if len(security) == 0:
        return True, RestAuthenticationClass.PUBLIC_UNAUTHENTICATED_READ_ONLY
    allows_anonymous = any(len(requirement) == 0 for requirement in security)
    if allows_anonymous:
        return True, RestAuthenticationClass.PUBLIC_UNAUTHENTICATED_READ_ONLY
    return False, RestAuthenticationClass.AUTHENTICATED_READ_ONLY


def _check_presence_flags_consistent(
    source: EffectiveSecuritySource,
    global_present: bool,
    operation_present: bool,
) -> None:
    if source is EffectiveSecuritySource.OPERATION_OVERRIDE:
        if operation_present is not True:
            raise _SourceConflictError(
                "OPERATION_OVERRIDE requires operation_security_key_present=true"
            )
    elif source is EffectiveSecuritySource.GLOBAL_INHERITED:
        if operation_present is not False or global_present is not True:
            raise _SourceConflictError(
                "GLOBAL_INHERITED requires operation_security_key_present=false "
                "and global_security_key_present=true"
            )
    elif source is EffectiveSecuritySource.NONE_DECLARED:
        if operation_present is not False or global_present is not False:
            raise _SourceConflictError(
                "NONE_DECLARED requires both presence flags to be false"
            )


def _parse_source_binding_record_bytes(record_bytes: bytes) -> dict:
    if type(record_bytes) is not bytes:
        raise _SourceIdentityUnboundError("source_binding_record_bytes must be bytes")
    try:
        text = record_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _SourceIdentityUnboundError(
            "source-binding record is not valid UTF-8"
        ) from exc
    try:
        record = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, ConnectivityError) as exc:
        raise _SourceIdentityUnboundError(
            "source-binding record is not valid JSON"
        ) from exc
    if not isinstance(record, dict):
        raise _SourceIdentityUnboundError(
            "source-binding record top level must be an object"
        )
    observed_fields = set(record.keys())
    unknown = observed_fields - _SOURCE_BINDING_RECORD_FIELDS
    if unknown:
        raise _SourceIdentityUnboundError(
            f"source-binding record contains unknown fields: {sorted(unknown)}"
        )
    missing = _SOURCE_BINDING_RECORD_FIELDS - observed_fields
    if missing:
        raise _SourceIdentityUnboundError(
            f"source-binding record is missing fields: {sorted(missing)}"
        )
    return record


def _derive_official_rest_source_binding_fields(
    record_bytes: bytes,
    expectation: ExecutionDispatchExpectation,
) -> dict:
    """Section 7.5 planner checks, items 4-10. The single authoritative
    derivation used both when a binding is first built during planning
    (`_build_official_rest_source_binding`) and every later time it is
    revalidated at a use-time consumption gate
    (`require_usable_official_rest_source_binding`) -- so construction
    and revalidation can never drift apart. Returns a plain dict keyed
    exactly by `OfficialRestSourceBinding`'s field names; raises
    `_SourceIdentityUnboundError`/`_SourceConflictError` on any failure."""

    require_usable_execution_dispatch_expectation(expectation)

    if type(record_bytes) is not bytes or len(record_bytes) == 0:
        raise _SourceIdentityUnboundError(
            "source_binding_record_bytes missing or empty"
        )

    observed_record_sha256 = hashlib.sha256(record_bytes).hexdigest()
    if observed_record_sha256 != expectation.expected_source_binding_record_sha256:
        raise _SourceIdentityUnboundError("source-binding record hash mismatch")

    record = _parse_source_binding_record_bytes(record_bytes)

    # The submitted bytes must themselves BE the exact canonical
    # serialization of the parsed record.
    if _canonical_record_bytes(record) != record_bytes:
        raise _SourceIdentityUnboundError(
            "source_binding_record_bytes is not the exact canonical "
            "serialization required by Section 5.5.3"
        )

    if not (_is_exact_int(record.get("schema_version")) and record["schema_version"] == 1):
        raise _SourceIdentityUnboundError(
            "source-binding record schema_version must be exact int 1"
        )
    if not (_is_exact_int(record.get("http_status")) and record["http_status"] == 200):
        raise _SourceIdentityUnboundError(
            "source-binding record http_status must be exact int 200"
        )
    if record.get("source_url") != _EXPECTED_SOURCE_URL:
        raise _SourceIdentityUnboundError("source-binding record source_url mismatch")
    if record.get("operation_method") != _EXPECTED_OPERATION_METHOD:
        raise _SourceIdentityUnboundError(
            "source-binding record operation_method mismatch"
        )
    if record.get("operation_path") != _EXPECTED_OPERATION_PATH:
        raise _SourceIdentityUnboundError(
            "source-binding record operation_path mismatch"
        )
    if record.get("reviewed_demo_rest_origin") != DEMO_ORIGIN:
        raise _SourceIdentityUnboundError(
            "source-binding record reviewed_demo_rest_origin mismatch"
        )
    if record.get("reviewed_full_request_path") != DEMO_FULL_PATH:
        raise _SourceIdentityUnboundError(
            "source-binding record reviewed_full_request_path mismatch"
        )
    if not (
        _is_exact_int(record.get("binding_schema_revision"))
        and record["binding_schema_revision"] == _EXPECTED_BINDING_SCHEMA_REVISION
    ):
        raise _SourceIdentityUnboundError(
            "source-binding record binding_schema_revision is unknown"
        )

    raw_len = record.get("raw_openapi_byte_length")
    if not (_is_exact_int(raw_len) and raw_len > 0):
        raise _SourceIdentityUnboundError(
            "raw_openapi_byte_length must be a positive exact int"
        )

    raw_sha = record.get("raw_openapi_sha256")
    if not _is_sha256_hex(raw_sha):
        raise _SourceIdentityUnboundError(
            "raw_openapi_sha256 is malformed or placeholder"
        )
    if raw_sha != expectation.expected_raw_openapi_sha256:
        raise _SourceIdentityUnboundError(
            "record raw_openapi_sha256 does not equal expected_raw_openapi_sha256"
        )

    if not _is_lowercase_media_type(record.get("normalized_source_media_type")):
        raise _SourceIdentityUnboundError(
            "normalized_source_media_type must be a nonblank lowercase string"
        )
    if not _is_rfc3339_utc(record.get("retrieved_at_utc")):
        raise _SourceIdentityUnboundError(
            "retrieved_at_utc must be a strict-syntax RFC 3339 UTC timestamp"
        )

    global_present = record.get("global_security_key_present")
    operation_present = record.get("operation_security_key_present")
    if not _is_exact_bool(global_present) or not _is_exact_bool(operation_present):
        raise _SourceIdentityUnboundError(
            "global_security_key_present/operation_security_key_present must be "
            "exact booleans"
        )

    try:
        source = EffectiveSecuritySource(record.get("effective_security_source"))
    except ValueError as exc:
        raise _SourceIdentityUnboundError(
            "effective_security_source is unknown"
        ) from exc

    _check_presence_flags_consistent(source, global_present, operation_present)

    allows_anonymous, classification = _classify_effective_security(
        source, record.get("effective_security")
    )

    declared_anonymous = record.get("effective_allows_anonymous")
    if not _is_exact_bool(declared_anonymous) or declared_anonymous is not allows_anonymous:
        raise _SourceConflictError(
            "effective_allows_anonymous does not match recomputed value"
        )
    try:
        declared_classification = RestAuthenticationClass(
            record.get("effective_auth_classification")
        )
    except ValueError as exc:
        raise _SourceIdentityUnboundError(
            "effective_auth_classification is unknown"
        ) from exc
    if declared_classification is not classification:
        raise _SourceConflictError(
            "effective_auth_classification does not match recomputed value"
        )
    if classification is not RestAuthenticationClass.PUBLIC_UNAUTHENTICATED_READ_ONLY:
        raise _SourceConflictError(
            "recomputed effective_auth_classification is not public"
        )

    return {
        "source_url": record["source_url"],
        "retrieved_at_utc": record["retrieved_at_utc"],
        "raw_openapi_byte_length": raw_len,
        "raw_openapi_sha256": raw_sha,
        "source_binding_record_byte_length": len(record_bytes),
        "source_binding_record_sha256": observed_record_sha256,
        "operation_method": record["operation_method"],
        "operation_path": record["operation_path"],
        "effective_security_source": source,
        "effective_auth_classification": classification,
        "reviewed_demo_rest_origin": record["reviewed_demo_rest_origin"],
        "reviewed_full_request_path": record["reviewed_full_request_path"],
        "binding_schema_revision": record["binding_schema_revision"],
    }


def _build_official_rest_source_binding(
    record_bytes: bytes,
    expectation: ExecutionDispatchExpectation,
) -> OfficialRestSourceBinding:
    fields = _derive_official_rest_source_binding_fields(record_bytes, expectation)
    return OfficialRestSourceBinding(**fields)


def require_usable_official_rest_source_binding(
    binding: object,
    expectation: ExecutionDispatchExpectation,
    record_bytes: object,
) -> None:
    """Implementation 08 correction 1. Does not merely check that
    `binding`'s fields are individually well-typed or mutually
    consistent with each other (Implementation 07's redundant-copy
    "commitment" approach, which Marco correctly rejected). Instead,
    this mechanically proves that `binding` still corresponds exactly
    to the canonical source-binding-record bytes whose SHA-256 equals
    the *current* `expectation.expected_source_binding_record_sha256`:
    it rehashes `record_bytes` against that external expectation,
    re-parses/revalidates the record under the accepted canonical
    schema, recomputes every authoritative field from scratch via
    `_derive_official_rest_source_binding_fields` (the exact same
    function used when the binding was first built), and compares every
    one of `binding`'s current public fields -- by both exact type and
    value -- against its freshly recomputed authoritative counterpart.
    Any difference, of any field, raises before the next network
    action. `record_bytes` is retained connectivity-local immutable
    plan state (see `ConnectivityPreflightPlan.source_binding_record_bytes`);
    it is the same bytes the caller originally supplied, not a secret,
    key, or new trust root of any kind."""

    if type(binding) is not OfficialRestSourceBinding:
        raise ConnectivityTypeError(
            "source binding must have exact type OfficialRestSourceBinding"
        )
    if type(record_bytes) is not bytes:
        raise _SourceIdentityUnboundError(
            "retained source_binding_record_bytes must have exact type bytes"
        )

    # Implementation 10 correction 1: explicit exact-ASCII-lexeme
    # validation of the binding's current hash fields, in addition to
    # (not instead of) the exact-type/value comparison against the
    # freshly recomputed authoritative values below. The two checks are
    # complementary: this one rejects a mutated hash that is not even
    # syntactically a SHA-256 hex digest; the comparison below rejects
    # one that is syntactically valid but simply wrong.
    if not _is_sha256_hex(getattr(binding, "source_binding_record_sha256", None)):
        raise _SourceIdentityUnboundError(
            "source binding source_binding_record_sha256 is not an exact "
            "ASCII SHA-256 lowercase hex lexeme"
        )
    if not _is_sha256_hex(getattr(binding, "raw_openapi_sha256", None)):
        raise _SourceIdentityUnboundError(
            "source binding raw_openapi_sha256 is not an exact ASCII SHA-256 "
            "lowercase hex lexeme"
        )

    # Recomputing from record_bytes already exact-type-validates
    # `expectation` and re-verifies the record hash against
    # `expectation.expected_source_binding_record_sha256`; if
    # `record_bytes` was tampered with to a different (even if
    # otherwise well-formed) canonical record, the hash check below
    # fails closed here.
    authoritative = _derive_official_rest_source_binding_fields(record_bytes, expectation)

    for field_name, authoritative_value in authoritative.items():
        current_value = getattr(binding, field_name)
        if type(current_value) is not type(authoritative_value):
            raise _SourceIdentityUnboundError(
                f"source binding field {field_name!r} no longer has the exact "
                "type it was derived with"
            )
        if current_value != authoritative_value:
            raise _SourceIdentityUnboundError(
                f"source binding field {field_name!r} no longer matches the "
                "canonical source-binding record it was derived from"
            )


# ---------------------------------------------------------------------------
# Section 9.7 -- Verified DNS set.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class VerifiedDnsSet:
    host: str
    port: int
    addresses: Tuple[Tuple[int, str], ...]  # (ip_version, canonical text)
    selected_address: str
    selected_ip_version: int


def _address_is_acceptable(ip: "ipaddress.IPv4Address | ipaddress.IPv6Address") -> bool:
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_unspecified
        or ip.is_reserved
    ):
        return False
    return ip.is_global


def _deterministic_sorted(
    pairs: "set[Tuple[int, str]] | Tuple[Tuple[int, str], ...]",
) -> Tuple[Tuple[int, str], ...]:
    return tuple(
        sorted(
            pairs,
            key=lambda pair: (pair[0], ipaddress.ip_address(pair[1]).packed),
        )
    )


def _classify_dns_answer(
    raw_candidates: Tuple[Tuple[int, tuple], ...]
) -> Tuple[Tuple[int, str], ...]:
    """Implementation 10 correction 2. `raw_candidates` is exactly what
    `_resolve_addresses` returns: `(family, sockaddr)` pairs, with
    `family` the value `socket.getaddrinfo()` actually reported --
    never discarded or re-derived from the address text alone. Before
    any address is canonicalized, deduplicated, or sorted, every
    candidate must independently pass:

    * `family` is exactly `socket.AF_INET` or `socket.AF_INET6` (an
      unknown/unsupported family rejects the entire answer);
    * `sockaddr` is a tuple of the shape that family actually uses --
      `(host, port)` for `AF_INET`, `(host, port, flowinfo, scopeid)`
      for `AF_INET6` (a malformed sockaddr rejects the entire answer);
    * the address text at `sockaddr[0]` is an exact `str` that actually
      parses as an IP address matching that same version -- `AF_INET`
      must carry a real IPv4 address, `AF_INET6` a real IPv6 address (a
      family/address-version mismatch rejects the entire answer).

    Only once every candidate has passed all of the above does the
    existing `ANY_PROHIBITED_RESOLVED_ADDRESS -> DNS_VERIFICATION_FAILED`
    rule, deduplication, and deterministic `(IP version, packed bytes)`
    sorting run, exactly as before."""

    if not raw_candidates:
        raise ConnectivityError("DNS answer is empty")

    parsed: set[Tuple[int, str]] = set()
    for candidate in raw_candidates:
        if type(candidate) is not tuple or len(candidate) != 2:
            raise ConnectivityError(f"malformed DNS resolution candidate: {candidate!r}")
        family_value = candidate[0]
        # `socket.getaddrinfo()` reports family as `socket.AddressFamily`
        # (an IntEnum), not exactly the built-in `int` -- both are
        # accepted here (as is a plain built-in `int`, for test
        # fixtures), but `bool` and any other int-*subclass* (including
        # one overriding `__eq__` to spoof equality with `AF_INET`/
        # `AF_INET6` while holding a different actual value) are not.
        if type(family_value) not in (socket.AddressFamily, int):
            raise ConnectivityError(
                f"malformed DNS resolution candidate family: {family_value!r}"
            )
        family, sockaddr = candidate

        if family == socket.AF_INET:
            expected_sockaddr_len = 2
            expected_ip_version = 4
        elif family == socket.AF_INET6:
            expected_sockaddr_len = 4
            expected_ip_version = 6
        else:
            raise ConnectivityError(f"unsupported resolved address family: {family!r}")

        if type(sockaddr) is not tuple or len(sockaddr) != expected_sockaddr_len:
            raise ConnectivityError(f"malformed sockaddr for family {family!r}: {sockaddr!r}")

        raw_address_text = sockaddr[0]
        if type(raw_address_text) is not str:
            raise ConnectivityError(
                f"malformed sockaddr address text: {raw_address_text!r}"
            )
        try:
            ip = ipaddress.ip_address(raw_address_text)
        except ValueError as exc:
            raise ConnectivityError(
                f"unclassifiable DNS address: {raw_address_text!r}"
            ) from exc

        if ip.version != expected_ip_version:
            raise ConnectivityError(
                f"resolved address family {family!r} does not match parsed IP "
                f"version {ip.version!r} for {raw_address_text!r}"
            )
        if not _address_is_acceptable(ip):
            raise ConnectivityError(f"prohibited resolved address: {raw_address_text!r}")

        parsed.add((expected_ip_version, str(ip)))

    return _deterministic_sorted(parsed)


def require_usable_verified_dns_set(dns_set: object, host: str, port: int) -> None:
    if type(dns_set) is not VerifiedDnsSet:
        raise ConnectivityTypeError("dns set must have exact type VerifiedDnsSet")
    if type(dns_set.host) is not str or dns_set.host != host:
        raise ConnectivityError("verified DNS set host mismatch")
    if type(dns_set.port) is not int or isinstance(dns_set.port, bool) or dns_set.port != port:
        raise ConnectivityError("verified DNS set port mismatch")
    if type(dns_set.addresses) is not tuple or not dns_set.addresses:
        raise ConnectivityError("verified DNS set addresses must be a nonempty tuple")

    reclassified: "set[Tuple[int, str]]" = set()
    for entry in dns_set.addresses:
        if (
            type(entry) is not tuple
            or len(entry) != 2
            or type(entry[0]) is not int
            or type(entry[1]) is not str
        ):
            raise ConnectivityError("verified DNS set entry has the wrong shape")
        version, addr_text = entry
        try:
            ip = ipaddress.ip_address(addr_text)
        except ValueError as exc:
            raise ConnectivityError(
                f"verified DNS set contains an unclassifiable address: {addr_text!r}"
            ) from exc
        if not _address_is_acceptable(ip):
            raise ConnectivityError(
                f"verified DNS set contains a now-prohibited address: {addr_text!r}"
            )
        expected_version = 4 if ip.version == 4 else 6
        if version != expected_version:
            raise ConnectivityError("verified DNS set entry IP-version mismatch")
        reclassified.add((expected_version, str(ip)))

    if len(reclassified) != len(dns_set.addresses):
        raise ConnectivityError("verified DNS set contains duplicate addresses")

    recomputed_order = _deterministic_sorted(reclassified)
    if recomputed_order != dns_set.addresses:
        raise ConnectivityError(
            "verified DNS set is not in the required deterministic order"
        )

    expected_version, expected_address = recomputed_order[0]
    if dns_set.selected_address != expected_address:
        raise ConnectivityError("verified DNS set selected_address is not deterministic")
    if dns_set.selected_ip_version != expected_version:
        raise ConnectivityError(
            "verified DNS set selected_ip_version is inconsistent with selected_address"
        )
    if dns_set.selected_address not in {addr for _v, addr in dns_set.addresses}:
        raise ConnectivityError("selected address is not a member of the verified set")


# ---------------------------------------------------------------------------
# Section 7.1 -- planning input and plan.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConnectivityPreflightInput:
    validated_demo_profile: ValidatedDemoProfile
    task_capability_envelope: TaskAuthorizationCapabilityEnvelope
    execution_dispatch_expectation: ExecutionDispatchExpectation
    source_binding_record_bytes: bytes
    request_budget: int = _REQUEST_BUDGET
    overall_timeout_ms: int = _OVERALL_TIMEOUT_MS
    socket_stage_timeout_ms: int = _SOCKET_STAGE_TIMEOUT_MS


@dataclass(frozen=True, slots=True)
class ConnectivityPreflightPlan:
    """Section 9.1. `source_binding_record_bytes` is Implementation
    08's connectivity-local immutable plan state: the exact canonical
    record bytes the plan's `source_binding` was derived from, retained
    so `require_usable_official_rest_source_binding` can rehash/
    re-parse/recompute the authoritative binding fields from scratch at
    every use-time consumption gate rather than trusting a redundant
    mutable copy of any one field. It is the caller's own original
    input bytes -- not a secret, key, or new trust root."""

    profile: ValidatedDemoProfile
    capability_envelope: TaskAuthorizationCapabilityEnvelope
    execution_dispatch_expectation: ExecutionDispatchExpectation
    source_binding: OfficialRestSourceBinding
    source_binding_record_bytes: bytes
    host: str
    port: int
    base_path: str
    route: str
    full_path: str
    method: str
    request_budget: int
    retry_count: int
    redirects_enabled: bool
    proxy_enabled: bool
    ambient_session_enabled: bool
    overall_timeout_ms: int
    socket_stage_timeout_ms: int
    max_response_bytes: int


def _capability_permitted(envelope: TaskAuthorizationCapabilityEnvelope, name: str) -> bool:
    return getattr(envelope, name).value == "PERMITTED"


def _capability_prohibited(envelope: TaskAuthorizationCapabilityEnvelope, name: str) -> bool:
    return getattr(envelope, name).value == "PROHIBITED"


_PROHIBITED_ENVELOPE_FIELDS = (
    "demo_authenticated_reads",
    "demo_writes",
    "production_public_reads",
    "production_authenticated_reads",
    "production_writes",
    "credential_use",
    "account_funding",
    "code_changes",
    "tests",
    "repository_commits",
)


def require_usable_connectivity_preflight_plan(plan: object) -> None:
    if type(plan) is not ConnectivityPreflightPlan:
        raise ConnectivityTypeError("plan must have exact type ConnectivityPreflightPlan")

    require_usable_validated_demo_profile(plan.profile)
    require_usable_capability_envelope(plan.capability_envelope)

    envelope = plan.capability_envelope
    if not _capability_permitted(envelope, "network_access") or not _capability_permitted(
        envelope, "demo_public_reads"
    ):
        raise ConnectivityError(
            "plan.capability_envelope no longer permits network_access/demo_public_reads"
        )
    for prohibited_field in _PROHIBITED_ENVELOPE_FIELDS:
        if not _capability_prohibited(envelope, prohibited_field):
            raise ConnectivityError(
                f"plan.capability_envelope no longer prohibits {prohibited_field}"
            )

    require_usable_official_rest_source_binding(
        plan.source_binding,
        plan.execution_dispatch_expectation,
        plan.source_binding_record_bytes,
    )

    if not _is_exact_str(plan.host) or plan.host != DEMO_HOST:
        raise ConnectivityError("plan.host must be the exact built-in str Demo host")
    if not _is_exact_int(plan.port) or plan.port != DEMO_PORT:
        raise ConnectivityError("plan.port must be the exact built-in int 443")
    if not _is_exact_str(plan.base_path) or plan.base_path != DEMO_BASE_PATH:
        raise ConnectivityError(
            "plan.base_path must be the exact built-in str Demo base path"
        )
    if not _is_exact_str(plan.route) or plan.route != DEMO_ROUTE:
        raise ConnectivityError("plan.route must be the exact built-in str Demo route")
    if not _is_exact_str(plan.full_path) or plan.full_path != DEMO_FULL_PATH:
        raise ConnectivityError(
            "plan.full_path must be the exact built-in str Demo full path"
        )
    if not _is_exact_str(plan.method) or plan.method != "GET":
        raise ConnectivityError("plan.method must be the exact built-in str 'GET'")
    if not _is_exact_int(plan.request_budget) or plan.request_budget != _REQUEST_BUDGET:
        raise ConnectivityError("plan.request_budget must be exactly the exact int 1")
    if not _is_exact_int(plan.retry_count) or plan.retry_count != 0:
        raise ConnectivityError("plan.retry_count must be exactly the exact int 0")
    if plan.redirects_enabled is not False:
        raise ConnectivityError("plan.redirects_enabled must be False")
    if plan.proxy_enabled is not False:
        raise ConnectivityError("plan.proxy_enabled must be False")
    if plan.ambient_session_enabled is not False:
        raise ConnectivityError("plan.ambient_session_enabled must be False")
    if not _is_exact_int(plan.overall_timeout_ms) or plan.overall_timeout_ms != (
        _OVERALL_TIMEOUT_MS
    ):
        raise ConnectivityError(
            "plan.overall_timeout_ms must be the exact built-in int 10000"
        )
    if not _is_exact_int(plan.socket_stage_timeout_ms) or plan.socket_stage_timeout_ms != (
        _SOCKET_STAGE_TIMEOUT_MS
    ):
        raise ConnectivityError(
            "plan.socket_stage_timeout_ms must be the exact built-in int 5000"
        )
    if not _is_exact_int(plan.max_response_bytes) or plan.max_response_bytes != (
        _MAX_RESPONSE_BYTES
    ):
        raise ConnectivityError(
            "plan.max_response_bytes must be the exact built-in int 65536"
        )

    for forbidden in (
        "transport",
        "session",
        "resolver",
        "socket",
        "ssl_context",
        "client",
        "callback",
        "connection_factory",
    ):
        if hasattr(plan, forbidden):
            raise ConnectivityError(
                f"plan must not expose a transport-injection field: {forbidden}"
            )


def plan_demo_read_only_connectivity(
    plan_input: object,
) -> ConnectivityPreflightPlan | ConnectivityPreflightHalt:
    """Pure and offline: performs no DNS, socket, TLS, or HTTP activity
    of any kind."""

    if type(plan_input) is not ConnectivityPreflightInput:
        return _halt(
            ConnectivityHaltCode.EXECUTION_INPUT_TYPE_INVALID,
            ConnectivityStage.PLAN_INPUT,
            expected="ConnectivityPreflightInput",
            observed=type(plan_input).__name__,
        )

    try:
        require_usable_capability_envelope(plan_input.task_capability_envelope)
    except Exception:
        return _halt(
            ConnectivityHaltCode.CAPABILITY_NOT_AUTHORIZED,
            ConnectivityStage.CAPABILITY_ENVELOPE_VALIDATED,
        )
    envelope = plan_input.task_capability_envelope
    if not _capability_permitted(envelope, "network_access") or not _capability_permitted(
        envelope, "demo_public_reads"
    ):
        return _halt(
            ConnectivityHaltCode.CAPABILITY_NOT_AUTHORIZED,
            ConnectivityStage.CAPABILITY_ENVELOPE_VALIDATED,
            expected="network_access=PERMITTED,demo_public_reads=PERMITTED",
        )
    for prohibited_field in _PROHIBITED_ENVELOPE_FIELDS:
        if not _capability_prohibited(envelope, prohibited_field):
            return _halt(
                ConnectivityHaltCode.CAPABILITY_NOT_AUTHORIZED,
                ConnectivityStage.CAPABILITY_ENVELOPE_VALIDATED,
                expected=f"{prohibited_field}=PROHIBITED",
            )

    try:
        require_usable_execution_dispatch_expectation(
            plan_input.execution_dispatch_expectation
        )
    except ConnectivityTypeError:
        return _halt(
            ConnectivityHaltCode.EXECUTION_INPUT_TYPE_INVALID,
            ConnectivityStage.EXECUTION_DISPATCH_EXPECTATION_VALIDATED,
        )
    except ConnectivityError:
        return _halt(
            ConnectivityHaltCode.OFFICIAL_SOURCE_IDENTITY_UNBOUND,
            ConnectivityStage.EXECUTION_DISPATCH_EXPECTATION_VALIDATED,
        )

    try:
        require_usable_validated_demo_profile(plan_input.validated_demo_profile)
    except Exception:
        return _halt(
            ConnectivityHaltCode.ENVIRONMENT_ENDPOINT_MISMATCH,
            ConnectivityStage.PROFILE_VERIFIED,
        )
    profile = plan_input.validated_demo_profile
    if profile.rest.host in PRODUCTION_REST_HOSTS:
        return _halt(
            ConnectivityHaltCode.PRODUCTION_ACCESS_PROHIBITED,
            ConnectivityStage.PROFILE_VERIFIED,
            observed=profile.rest.host,
        )
    if profile.rest.host == DEMO_COMPATIBILITY_HOST:
        return _halt(
            ConnectivityHaltCode.ENDPOINT_NOT_ALLOWLISTED,
            ConnectivityStage.PROFILE_VERIFIED,
            observed=profile.rest.host,
        )
    if profile.rest.host != DEMO_HOST:
        return _halt(
            ConnectivityHaltCode.ENDPOINT_NOT_ALLOWLISTED,
            ConnectivityStage.PROFILE_VERIFIED,
            observed=profile.rest.host,
        )

    try:
        source_binding = _build_official_rest_source_binding(
            plan_input.source_binding_record_bytes,
            plan_input.execution_dispatch_expectation,
        )
    except _SourceConflictError:
        return _halt(
            ConnectivityHaltCode.OFFICIAL_SOURCE_CONFLICT,
            ConnectivityStage.SOURCE_RECORD_IDENTITY_VERIFIED,
        )
    except ConnectivityError:
        return _halt(
            ConnectivityHaltCode.OFFICIAL_SOURCE_IDENTITY_UNBOUND,
            ConnectivityStage.SOURCE_RECORD_IDENTITY_VERIFIED,
        )

    if (
        source_binding.effective_auth_classification
        is not RestAuthenticationClass.PUBLIC_UNAUTHENTICATED_READ_ONLY
    ):
        return _halt(
            ConnectivityHaltCode.OFFICIAL_SOURCE_CONFLICT,
            ConnectivityStage.SOURCE_RECORD_IDENTITY_VERIFIED,
        )

    request_budget = plan_input.request_budget
    overall_timeout_ms = plan_input.overall_timeout_ms
    socket_stage_timeout_ms = plan_input.socket_stage_timeout_ms
    if not _is_exact_int(request_budget) or request_budget != _REQUEST_BUDGET:
        return _halt(
            ConnectivityHaltCode.EXECUTION_INPUT_TYPE_INVALID,
            ConnectivityStage.PLAN_INPUT,
            expected="request_budget=1",
        )
    if (
        not _is_exact_int(overall_timeout_ms)
        or overall_timeout_ms != _OVERALL_TIMEOUT_MS
        or not _is_exact_int(socket_stage_timeout_ms)
        or socket_stage_timeout_ms != _SOCKET_STAGE_TIMEOUT_MS
    ):
        return _halt(
            ConnectivityHaltCode.EXECUTION_INPUT_TYPE_INVALID,
            ConnectivityStage.PLAN_INPUT,
            expected="overall_timeout_ms=10000,socket_stage_timeout_ms=5000",
        )

    plan = ConnectivityPreflightPlan(
        profile=profile,
        capability_envelope=envelope,
        execution_dispatch_expectation=plan_input.execution_dispatch_expectation,
        source_binding=source_binding,
        source_binding_record_bytes=plan_input.source_binding_record_bytes,
        host=DEMO_HOST,
        port=DEMO_PORT,
        base_path=DEMO_BASE_PATH,
        route=DEMO_ROUTE,
        full_path=DEMO_FULL_PATH,
        method="GET",
        request_budget=_REQUEST_BUDGET,
        retry_count=0,
        redirects_enabled=False,
        proxy_enabled=False,
        ambient_session_enabled=False,
        overall_timeout_ms=_OVERALL_TIMEOUT_MS,
        socket_stage_timeout_ms=_SOCKET_STAGE_TIMEOUT_MS,
        max_response_bytes=_MAX_RESPONSE_BYTES,
    )

    try:
        require_usable_connectivity_preflight_plan(plan)
    except Exception:
        return _halt(
            ConnectivityHaltCode.EXECUTION_PLAN_MUTATED,
            ConnectivityStage.SOURCE_BOUND,
        )

    return plan


# ---------------------------------------------------------------------------
# Section 7.6 -- successful result.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConnectivityPreflightSuccess:
    result_code: str
    environment: str
    method: str
    route: str
    full_path: str
    origin_host_classification: str
    request_count: int
    retry_count: int
    http_status: int
    response_media_type: str
    response_byte_length: int
    response_sha256: str
    exchange_active: bool
    trading_active: bool

    dns_verification_result: str
    resolver_returned_address_count: int
    verified_dns_address_count: int
    selected_numeric_address: str
    selected_address_family: int
    no_prohibited_address_confirmed: bool
    no_hostname_reresolution_confirmed: bool

    tls_verification_result: str
    negotiated_tls_version: str

    raw_openapi_sha256: str
    raw_openapi_byte_length: int
    source_binding_record_sha256: str
    source_binding_record_byte_length: int
    effective_security_source: str

    start_timestamp_utc: str
    end_timestamp_utc: str
    caller_visible_elapsed_ms: int
    resolver_abandoned: bool
    authorization_provenance_mode: ExecutionProvenanceMode
    runtime_authorization_provenance_proof: RuntimeProvenanceProof

    credentials_read: int = 0
    auth_headers_sent: int = 0
    redirects_followed: int = 0
    writes: int = 0
    orders: int = 0
    cancellations: int = 0
    funding_actions: int = 0
    websocket_connections: int = 0
    production_requests: int = 0
    polymarket_requests: int = 0


# ---------------------------------------------------------------------------
# Section 9.6.1/15.4 -- least-privilege, single-use DNS resolver worker.
#
# A fresh `threading.Thread(daemon=True)` is spawned for every call --
# never a reusable pool -- so the worker is never reused and its
# lifecycle cannot outlive or be confused with another call's. The
# worker receives only `host`/`port`; it has no access to the plan,
# capability envelope, source binding, transport, or any callback. Its
# only output is a value placed into a private `queue.Queue(maxsize=1)`
# that only this call's main thread will ever read from, and only until
# it stops waiting. `daemon=True` means process exit does not wait for
# it either.
# ---------------------------------------------------------------------------


def _resolve_addresses(host: str, port: int) -> Tuple[Tuple[int, tuple], ...]:
    """Implementation 10 correction 2: preserves the address `family`
    `socket.getaddrinfo()` actually returned for each candidate,
    together with its raw `sockaddr` tuple, instead of discarding both
    and keeping only the address text. Downstream classification
    (`_classify_dns_answer`) uses the family to cross-validate against
    the address text it parses from `sockaddr`, rather than trusting
    the text alone."""

    infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    return tuple((family, sockaddr) for family, _type, _proto, _canon, sockaddr in infos)


def _dns_resolver_worker(host: str, port: int, result_channel: "queue.Queue") -> None:
    try:
        addresses = _resolve_addresses(host, port)
    except Exception as exc:  # noqa: BLE001 - classified by the caller
        try:
            result_channel.put_nowait(("error", exc))
        except queue.Full:
            pass
        return
    try:
        result_channel.put_nowait(("ok", addresses))
    except queue.Full:
        pass


def _resolve_addresses_with_deadline(
    host: str, port: int, timeout_s: float
) -> Tuple[Tuple[int, tuple], ...]:
    """Section 9.6.1. Spawns one private daemon worker for this call
    only, waits for at most `timeout_s`, and -- if the deadline expires
    first -- returns without joining the worker or waiting for it in any
    way. A late result is left unread in the abandoned queue."""

    if timeout_s <= 0:
        raise TimeoutError("no time remained for DNS resolution")

    result_channel: "queue.Queue" = queue.Queue(maxsize=1)
    worker = threading.Thread(
        target=_dns_resolver_worker,
        args=(host, port, result_channel),
        daemon=True,
        name="kalshi-demo-preflight-dns-resolver",
    )
    worker.start()
    try:
        kind, payload = result_channel.get(timeout=timeout_s)
    except queue.Empty:
        # Deadline expired. Do not join, do not wait for shutdown, do
        # not wait for cancellation acknowledgement, do not start a
        # replacement resolver. The worker may still be running; its
        # eventual result (if any) is never read by anyone.
        raise TimeoutError("DNS resolution exceeded the caller-visible deadline") from None
    if kind == "error":
        raise payload
    return payload


def _connect_tcp(address: str, port: int, family: int, timeout_s: float) -> socket.socket:
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.settimeout(timeout_s)
    sock.connect((address, port))
    return sock


def _tls_wrap(raw_sock: socket.socket, server_hostname: str, timeout_s: float) -> ssl.SSLSocket:
    """The timeout is set on the *raw* socket before `wrap_socket(...)`
    is called, since `wrap_socket()` performs the handshake
    synchronously while it executes."""

    raw_sock.settimeout(timeout_s)
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    tls_sock = context.wrap_socket(raw_sock, server_hostname=server_hostname)
    return tls_sock


def _send_request(tls_sock: ssl.SSLSocket, host: str, full_path: str, timeout_s: float) -> None:
    tls_sock.settimeout(max(timeout_s, 0.0))
    request = (
        f"GET {full_path} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        "Accept: application/json\r\n"
        "Accept-Encoding: identity\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).encode("ascii")
    tls_sock.sendall(request)


def _receive_response(
    tls_sock: ssl.SSLSocket, max_bytes: int, deadline_ns: int, socket_stage_timeout_ms: int
) -> bytes:
    """Section 9.6.3: each individual `recv()` timeout is
    `min(socket_stage_timeout_ms / 1000, remaining_overall_s)`,
    recomputed immediately before every call -- not the full remaining
    overall budget alone. A response that is still trickling in after
    more than the overall deadline allows still halts at the overall
    deadline; a response trickling in slowly but within the overall
    deadline is still bounded to no more than the 5000 ms socket-stage
    cap per individual read."""

    stage_timeout_s = socket_stage_timeout_ms / 1000.0
    chunks = []
    total = 0
    hard_cap = max_bytes + 8192
    while True:
        remaining_overall_s = (deadline_ns - _current_monotonic_ns()) / 1_000_000_000.0
        if remaining_overall_s <= 0:
            raise socket.timeout("overall deadline exceeded during response read")
        remaining_s = min(stage_timeout_s, remaining_overall_s)
        tls_sock.settimeout(remaining_s)
        chunk = tls_sock.recv(4096)
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > hard_cap:
            break
    return b"".join(chunks)


def _negotiated_tls_version(tls_sock: ssl.SSLSocket) -> str:
    return tls_sock.version() or "UNKNOWN"


# ---------------------------------------------------------------------------
# Section 9.2/9.6 -- production execution boundary.
# ---------------------------------------------------------------------------


def _current_monotonic_ns() -> int:
    return time.monotonic_ns()


def _remaining_ns(deadline_ns: int) -> int:
    return deadline_ns - _current_monotonic_ns()


def _revalidate_all_gates(plan: ConnectivityPreflightPlan) -> None:
    require_usable_connectivity_preflight_plan(plan)


def execute_demo_read_only_connectivity(
    plan: object,
) -> ConnectivityPreflightSuccess | ConnectivityPreflightHalt:
    """Section 9.2/9.6. Accepts only `plan`. The `10000 ms` caller-visible
    deadline begins at the first instruction below, before any
    production current-value gate."""

    start_monotonic_ns = _current_monotonic_ns()
    deadline_ns = start_monotonic_ns + _OVERALL_TIMEOUT_MS * 1_000_000
    start_ts = datetime.now(timezone.utc).isoformat()

    def _elapsed_ms() -> int:
        return int((_current_monotonic_ns() - start_monotonic_ns) / 1_000_000)

    if type(plan) is not ConnectivityPreflightPlan:
        return _halt(
            ConnectivityHaltCode.EXECUTION_INPUT_TYPE_INVALID,
            ConnectivityStage.PLAN_INPUT,
            expected="ConnectivityPreflightPlan",
            observed=type(plan).__name__,
            caller_visible_elapsed_ms=_elapsed_ms(),
        )

    envelope = plan.capability_envelope
    try:
        require_usable_capability_envelope(envelope)
    except Exception:
        return _halt(
            ConnectivityHaltCode.EXECUTION_CAPABILITY_NOT_AUTHORIZED,
            ConnectivityStage.CAPABILITY_ENVELOPE_VALIDATED,
            caller_visible_elapsed_ms=_elapsed_ms(),
        )
    if not _capability_permitted(envelope, "network_access") or not _capability_permitted(
        envelope, "demo_public_reads"
    ):
        return _halt(
            ConnectivityHaltCode.EXECUTION_CAPABILITY_NOT_AUTHORIZED,
            ConnectivityStage.CAPABILITY_ENVELOPE_VALIDATED,
            caller_visible_elapsed_ms=_elapsed_ms(),
        )

    # Gate 1: immediately before DNS.
    try:
        _revalidate_all_gates(plan)
    except Exception:
        return _halt(
            ConnectivityHaltCode.EXECUTION_PLAN_MUTATED,
            ConnectivityStage.PRE_DNS_CURRENT_VALUES_REVERIFIED,
            caller_visible_elapsed_ms=_elapsed_ms(),
        )

    # Section 9.6.1: DNS waits for the full positive remaining overall
    # budget -- the 5000 ms socket_stage_timeout_ms cap applies only to
    # the later TCP/TLS/send/read stages (Section 9.6.3), not to DNS.
    remaining_s = _remaining_ns(deadline_ns) / 1_000_000_000.0
    if remaining_s <= 0:
        return _halt(
            ConnectivityHaltCode.CONNECTIVITY_TIMEOUT,
            ConnectivityStage.DNS_RESOLUTION_WAIT,
            caller_visible_elapsed_ms=_elapsed_ms(),
            resolver_abandoned=False,
        )

    try:
        raw_addresses = _resolve_addresses_with_deadline(plan.host, plan.port, remaining_s)
    except TimeoutError:
        return _halt(
            ConnectivityHaltCode.CONNECTIVITY_TIMEOUT,
            ConnectivityStage.DNS_RESOLUTION_WAIT,
            request_count=0,
            retry_count=0,
            caller_visible_elapsed_ms=_elapsed_ms(),
            resolver_abandoned=True,
        )
    except OSError:
        return _halt(
            ConnectivityHaltCode.DNS_VERIFICATION_FAILED,
            ConnectivityStage.DNS_RESOLVED,
            caller_visible_elapsed_ms=_elapsed_ms(),
        )

    resolver_returned_count = len(raw_addresses)

    try:
        verified_pairs = _classify_dns_answer(raw_addresses)
    except ConnectivityError:
        return _halt(
            ConnectivityHaltCode.DNS_VERIFICATION_FAILED,
            ConnectivityStage.DNS_SET_VERIFIED,
            caller_visible_elapsed_ms=_elapsed_ms(),
        )

    selected_version, selected_address = verified_pairs[0]
    dns_set = VerifiedDnsSet(
        host=plan.host,
        port=plan.port,
        addresses=verified_pairs,
        selected_address=selected_address,
        selected_ip_version=selected_version,
    )
    try:
        require_usable_verified_dns_set(dns_set, plan.host, plan.port)
    except Exception:
        return _halt(
            ConnectivityHaltCode.DNS_VERIFICATION_FAILED,
            ConnectivityStage.DNS_SET_VERIFIED,
            caller_visible_elapsed_ms=_elapsed_ms(),
        )

    # Gate 2: immediately after DNS-set verification, before socket
    # creation.
    try:
        _revalidate_all_gates(plan)
        require_usable_verified_dns_set(dns_set, plan.host, plan.port)
    except Exception:
        return _halt(
            ConnectivityHaltCode.EXECUTION_PLAN_MUTATED,
            ConnectivityStage.PRE_SOCKET_CURRENT_VALUES_REVERIFIED,
            caller_visible_elapsed_ms=_elapsed_ms(),
        )

    remaining_s = min(
        _remaining_ns(deadline_ns) / 1_000_000_000.0, plan.socket_stage_timeout_ms / 1000.0
    )
    if remaining_s <= 0:
        return _halt(
            ConnectivityHaltCode.CONNECTIVITY_TIMEOUT,
            ConnectivityStage.PRE_SOCKET_CURRENT_VALUES_REVERIFIED,
            caller_visible_elapsed_ms=_elapsed_ms(),
        )

    family = socket.AF_INET if selected_version == 4 else socket.AF_INET6
    try:
        raw_sock = _connect_tcp(selected_address, plan.port, family, remaining_s)
    except socket.timeout:
        return _halt(
            ConnectivityHaltCode.CONNECTIVITY_TIMEOUT,
            ConnectivityStage.TCP_CONNECTED_TO_PINNED_ADDRESS,
            caller_visible_elapsed_ms=_elapsed_ms(),
        )
    except OSError:
        return _halt(
            ConnectivityHaltCode.TRANSPORT_FAILURE,
            ConnectivityStage.TCP_CONNECTED_TO_PINNED_ADDRESS,
            caller_visible_elapsed_ms=_elapsed_ms(),
        )

    remaining_s = min(
        _remaining_ns(deadline_ns) / 1_000_000_000.0, plan.socket_stage_timeout_ms / 1000.0
    )
    if remaining_s <= 0:
        raw_sock.close()
        return _halt(
            ConnectivityHaltCode.CONNECTIVITY_TIMEOUT,
            ConnectivityStage.TLS_VERIFIED_FOR_DEMO_HOSTNAME,
            caller_visible_elapsed_ms=_elapsed_ms(),
        )
    try:
        tls_sock = _tls_wrap(raw_sock, plan.host, remaining_s)
    except socket.timeout:
        raw_sock.close()
        return _halt(
            ConnectivityHaltCode.CONNECTIVITY_TIMEOUT,
            ConnectivityStage.TLS_VERIFIED_FOR_DEMO_HOSTNAME,
            caller_visible_elapsed_ms=_elapsed_ms(),
        )
    except ssl.SSLError:
        raw_sock.close()
        return _halt(
            ConnectivityHaltCode.TLS_VERIFICATION_FAILED,
            ConnectivityStage.TLS_VERIFIED_FOR_DEMO_HOSTNAME,
            caller_visible_elapsed_ms=_elapsed_ms(),
        )
    except OSError:
        raw_sock.close()
        return _halt(
            ConnectivityHaltCode.TLS_VERIFICATION_FAILED,
            ConnectivityStage.TLS_VERIFIED_FOR_DEMO_HOSTNAME,
            caller_visible_elapsed_ms=_elapsed_ms(),
        )

    negotiated_version = _negotiated_tls_version(tls_sock)
    if negotiated_version in ("SSLv3", "TLSv1", "TLSv1.1"):
        tls_sock.close()
        return _halt(
            ConnectivityHaltCode.TLS_VERIFICATION_FAILED,
            ConnectivityStage.TLS_VERIFIED_FOR_DEMO_HOSTNAME,
            observed=negotiated_version,
            caller_visible_elapsed_ms=_elapsed_ms(),
        )

    # Gate 3: immediately before the HTTP send.
    try:
        _revalidate_all_gates(plan)
    except Exception:
        tls_sock.close()
        return _halt(
            ConnectivityHaltCode.EXECUTION_PLAN_MUTATED,
            ConnectivityStage.PRE_SEND_CURRENT_VALUES_REVERIFIED,
            caller_visible_elapsed_ms=_elapsed_ms(),
        )

    if plan.request_budget != _REQUEST_BUDGET:
        tls_sock.close()
        return _halt(
            ConnectivityHaltCode.REQUEST_BUDGET_EXHAUSTED,
            ConnectivityStage.PRE_SEND_CURRENT_VALUES_REVERIFIED,
            caller_visible_elapsed_ms=_elapsed_ms(),
        )

    # Section 9.6.3: the 5000 ms socket-stage cap subordinates the send
    # to min(stage_cap, remaining_overall) -- same as TCP connect and
    # TLS handshake above, not the full remaining overall budget alone.
    remaining_s = min(
        _remaining_ns(deadline_ns) / 1_000_000_000.0, plan.socket_stage_timeout_ms / 1000.0
    )
    if remaining_s <= 0:
        tls_sock.close()
        return _halt(
            ConnectivityHaltCode.CONNECTIVITY_TIMEOUT,
            ConnectivityStage.PRE_SEND_CURRENT_VALUES_REVERIFIED,
            caller_visible_elapsed_ms=_elapsed_ms(),
        )

    request_count = 1
    try:
        _send_request(tls_sock, plan.host, plan.full_path, remaining_s)
    except socket.timeout:
        tls_sock.close()
        return _halt(
            ConnectivityHaltCode.CONNECTIVITY_TIMEOUT,
            ConnectivityStage.REQUEST_SENT,
            request_count=request_count,
            caller_visible_elapsed_ms=_elapsed_ms(),
        )
    except OSError:
        # Finding 3: once the single send attempt has begun,
        # `sendall()` may raise after having already written some
        # bytes to the socket -- there is no portable way to prove zero
        # bytes were transmitted. Treat this the same as any other
        # interruption after the request attempt starts and before
        # terminal response classification (Section 14.3):
        # REQUEST_RESULT_UNKNOWN, never a silently-clean TRANSPORT_FAILURE
        # and never an automatic resend.
        tls_sock.close()
        return _halt(
            ConnectivityHaltCode.REQUEST_RESULT_UNKNOWN,
            ConnectivityStage.REQUEST_SENT,
            request_count=request_count,
            retry_count=0,
            caller_visible_elapsed_ms=_elapsed_ms(),
        )

    if _remaining_ns(deadline_ns) <= 0:
        tls_sock.close()
        return _halt(
            ConnectivityHaltCode.CONNECTIVITY_TIMEOUT,
            ConnectivityStage.RESPONSE_HEADERS_RECEIVED,
            request_count=request_count,
            caller_visible_elapsed_ms=_elapsed_ms(),
        )

    try:
        raw_response = _receive_response(
            tls_sock, plan.max_response_bytes, deadline_ns, plan.socket_stage_timeout_ms
        )
    except socket.timeout:
        tls_sock.close()
        return _halt(
            ConnectivityHaltCode.CONNECTIVITY_TIMEOUT,
            ConnectivityStage.RESPONSE_HEADERS_RECEIVED,
            request_count=request_count,
            caller_visible_elapsed_ms=_elapsed_ms(),
        )
    except OSError:
        tls_sock.close()
        return _halt(
            ConnectivityHaltCode.REQUEST_RESULT_UNKNOWN,
            ConnectivityStage.RESPONSE_HEADERS_RECEIVED,
            request_count=request_count,
            caller_visible_elapsed_ms=_elapsed_ms(),
        )
    finally:
        try:
            tls_sock.close()
        except OSError:
            pass

    if _remaining_ns(deadline_ns) < 0:
        return _halt(
            ConnectivityHaltCode.CONNECTIVITY_TIMEOUT,
            ConnectivityStage.RESPONSE_VALIDATED,
            request_count=request_count,
            caller_visible_elapsed_ms=_elapsed_ms(),
        )

    result = _validate_response(raw_response, plan.max_response_bytes)
    if isinstance(result, ConnectivityPreflightHalt):
        return ConnectivityPreflightHalt(
            code=result.code,
            stage=result.stage,
            expected=result.expected,
            observed=result.observed,
            request_count=request_count,
            retry_count=0,
            caller_visible_elapsed_ms=_elapsed_ms(),
        )

    (
        status,
        media_type,
        body_bytes,
        exchange_active,
        trading_active,
    ) = result

    # Finding 1: recompute the absolute monotonic remaining budget
    # after parsing/classification has actually run, immediately before
    # constructing or returning success. `deadline_ns` is not reset or
    # recreated here -- this is the same single deadline established at
    # function entry, just checked again at this later point, since
    # parsing/classification itself consumes real wall-clock time that
    # the earlier pre-parse check could not account for.
    if _remaining_ns(deadline_ns) <= 0:
        return _halt(
            ConnectivityHaltCode.CONNECTIVITY_TIMEOUT,
            ConnectivityStage.RESPONSE_VALIDATED,
            request_count=request_count,
            retry_count=0,
            caller_visible_elapsed_ms=_elapsed_ms(),
        )

    end_ts = datetime.now(timezone.utc).isoformat()

    return ConnectivityPreflightSuccess(
        result_code="DEMO_REST_CONNECTIVITY_CONFIRMED",
        environment="KALSHI_DEMO",
        method="GET",
        route=DEMO_ROUTE,
        full_path=DEMO_FULL_PATH,
        origin_host_classification="RECOMMENDED_DEMO_REST",
        request_count=request_count,
        retry_count=0,
        http_status=status,
        response_media_type=media_type,
        response_byte_length=len(body_bytes),
        response_sha256=hashlib.sha256(body_bytes).hexdigest(),
        exchange_active=exchange_active,
        trading_active=trading_active,
        dns_verification_result="VERIFIED",
        resolver_returned_address_count=resolver_returned_count,
        verified_dns_address_count=len(dns_set.addresses),
        selected_numeric_address=selected_address,
        selected_address_family=selected_version,
        no_prohibited_address_confirmed=True,
        no_hostname_reresolution_confirmed=True,
        tls_verification_result="VERIFIED",
        negotiated_tls_version=negotiated_version,
        raw_openapi_sha256=plan.source_binding.raw_openapi_sha256,
        raw_openapi_byte_length=plan.source_binding.raw_openapi_byte_length,
        source_binding_record_sha256=plan.source_binding.source_binding_record_sha256,
        source_binding_record_byte_length=(
            plan.source_binding.source_binding_record_byte_length
        ),
        effective_security_source=plan.source_binding.effective_security_source.value,
        start_timestamp_utc=start_ts,
        end_timestamp_utc=end_ts,
        caller_visible_elapsed_ms=_elapsed_ms(),
        resolver_abandoned=False,
        authorization_provenance_mode=(
            ExecutionProvenanceMode.EXTERNAL_GUSTAVO_ORCHESTRATION
        ),
        runtime_authorization_provenance_proof=(
            RuntimeProvenanceProof.NOT_PERFORMED_BY_DESIGN
        ),
    )


def _validate_response(raw_response: bytes, max_body_bytes: int):
    separator = b"\r\n\r\n"
    if separator not in raw_response:
        return _halt(
            ConnectivityHaltCode.RESPONSE_MALFORMED,
            ConnectivityStage.RESPONSE_HEADERS_RECEIVED,
        )
    header_blob, _, body = raw_response.partition(separator)
    try:
        header_text = header_blob.decode("ascii")
    except UnicodeDecodeError:
        return _halt(
            ConnectivityHaltCode.RESPONSE_MALFORMED,
            ConnectivityStage.RESPONSE_HEADERS_RECEIVED,
        )
    lines = header_text.split("\r\n")
    status_line = lines[0]
    parts = status_line.split(" ", 2)
    if len(parts) < 2 or not parts[1].isdigit():
        return _halt(
            ConnectivityHaltCode.RESPONSE_MALFORMED,
            ConnectivityStage.RESPONSE_HEADERS_RECEIVED,
        )
    status = int(parts[1])

    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line or ":" not in line:
            continue
        name, _, value = line.partition(":")
        headers[name.strip().lower()] = value.strip()

    if 300 <= status <= 399:
        return _halt(
            ConnectivityHaltCode.ENDPOINT_REDIRECT_PROHIBITED,
            ConnectivityStage.RESPONSE_HEADERS_RECEIVED,
            observed=str(status),
        )
    if status in (401, 403):
        return _halt(
            ConnectivityHaltCode.UNEXPECTED_AUTHENTICATION_REQUIREMENT,
            ConnectivityStage.RESPONSE_HEADERS_RECEIVED,
            observed=str(status),
        )
    if status != 200:
        return _halt(
            ConnectivityHaltCode.UNEXPECTED_HTTP_STATUS,
            ConnectivityStage.RESPONSE_HEADERS_RECEIVED,
            observed=str(status),
        )

    content_encoding = headers.get("content-encoding", "identity")
    if content_encoding.lower() not in ("identity", ""):
        return _halt(
            ConnectivityHaltCode.RESPONSE_MALFORMED,
            ConnectivityStage.RESPONSE_VALIDATED,
            observed=content_encoding,
        )

    content_type = headers.get("content-type", "")
    media_type = content_type.split(";", 1)[0].strip().lower()
    if media_type != "application/json":
        return _halt(
            ConnectivityHaltCode.RESPONSE_MALFORMED,
            ConnectivityStage.RESPONSE_VALIDATED,
            observed=media_type or "<absent>",
        )

    if len(body) > max_body_bytes:
        return _halt(
            ConnectivityHaltCode.RESPONSE_MALFORMED,
            ConnectivityStage.RESPONSE_VALIDATED,
            observed=str(len(body)),
        )

    try:
        body_text = body.decode("utf-8")
    except UnicodeDecodeError:
        return _halt(
            ConnectivityHaltCode.RESPONSE_MALFORMED,
            ConnectivityStage.RESPONSE_VALIDATED,
        )
    try:
        payload = json.loads(body_text, parse_constant=_reject_json_constant)
    except (json.JSONDecodeError, ConnectivityError):
        return _halt(
            ConnectivityHaltCode.RESPONSE_MALFORMED,
            ConnectivityStage.RESPONSE_VALIDATED,
        )
    if not isinstance(payload, dict):
        return _halt(
            ConnectivityHaltCode.RESPONSE_MALFORMED,
            ConnectivityStage.RESPONSE_VALIDATED,
        )
    if "exchange_active" not in payload or "trading_active" not in payload:
        return _halt(
            ConnectivityHaltCode.RESPONSE_MALFORMED,
            ConnectivityStage.RESPONSE_VALIDATED,
        )
    exchange_active = payload["exchange_active"]
    trading_active = payload["trading_active"]
    if type(exchange_active) is not bool or type(trading_active) is not bool:
        return _halt(
            ConnectivityHaltCode.RESPONSE_MALFORMED,
            ConnectivityStage.RESPONSE_VALIDATED,
        )

    return status, media_type, body, exchange_active, trading_active
