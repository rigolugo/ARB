"""Pure, offline, non-secret validation for the Kalshi Demo environment,
endpoint, capability-envelope, and credential-source-name contract
(Candidate 02).

This module constructs no HTTP or WebSocket client, no signer, no
transport, and no credential loader. It performs no DNS resolution, no
socket activity, and no environment-variable read. It stops at the first
primary halt per the exact precedence in Candidate 02 Section 20.2 and
produces exactly one `ValidationResult`.

`validate()` is a public consumption boundary for the capability
envelope: it applies `models.require_usable_capability_envelope`, which
enforces the exact runtime type and revalidates the complete field
invariant from current values. Any failure becomes the existing safe
`CAPABILITY_FIELD_MISSING` halt with non-secret classification metadata;
no raw exception content is propagated.
"""

from __future__ import annotations

from urllib.parse import SplitResult, urlsplit

from .errors import HaltCode, TypedHalt
from .models import (
    AuthorizationValue,
    CapabilityEnvelopeError,
    CredentialReferenceKind,
    CredentialReferenceState,
    CredentialSourceReference,
    EndpointComponents,
    EndpointProfile,
    Environment,
    NonSecretConfigurationInput,
    RequestedCapability,
    ValidatedDemoProfile,
    ValidationResult,
    ValidationStage,
    require_usable_capability_envelope,
)

# ---------------------------------------------------------------------------
# Exact endpoint allowlist (Candidate 02 Section 14.1 / handoff Section 6).
# ---------------------------------------------------------------------------

_ALLOWED_PORT = 443
_DEFAULT_PORT_BY_SCHEME = {"https": 443, "wss": 443}

_DEMO_REST = EndpointComponents(
    scheme="https",
    host="external-api.demo.kalshi.co",
    port=_ALLOWED_PORT,
    path="/trade-api/v2",
    has_user_info=False,
    has_query=False,
    has_fragment=False,
)

_DEMO_WEBSOCKET = EndpointComponents(
    scheme="wss",
    host="external-api-ws.demo.kalshi.co",
    port=_ALLOWED_PORT,
    path="/trade-api/ws/v2",
    has_user_info=False,
    has_query=False,
    has_fragment=False,
)

# Recognized solely so a mismatch can be diagnosed deterministically. Never
# accepted; never used to construct anything.
_PRODUCTION_REST_HOST = "external-api.kalshi.com"
_PRODUCTION_WEBSOCKET_HOST = "external-api-ws.kalshi.com"

_ACCEPTED_CREDENTIAL_SOURCE_NAMES = {
    CredentialReferenceKind.API_KEY_ID_ENV_SOURCE: "KALSHI_DEMO_API_KEY_ID",
    CredentialReferenceKind.PRIVATE_KEY_PEM_ENV_SOURCE: "KALSHI_DEMO_PRIVATE_KEY_PEM",
}

_REQUIRED_CREDENTIAL_KINDS = (
    CredentialReferenceKind.API_KEY_ID_ENV_SOURCE,
    CredentialReferenceKind.PRIVATE_KEY_PEM_ENV_SOURCE,
)

_ENVIRONMENT_VALUES = {member.value for member in Environment}
_REQUESTED_CAPABILITY_VALUES = {member.value for member in RequestedCapability}

_PRODUCTION_REQUESTED_CAPABILITIES = {
    RequestedCapability.PRODUCTION_PUBLIC_REST_READ,
    RequestedCapability.PRODUCTION_AUTHENTICATED_READ,
    RequestedCapability.PRODUCTION_WRITE,
}


def _halt(
    code: HaltCode,
    stage: ValidationStage,
    *,
    field_name: str | None = None,
    expected: str | None = None,
    observed: str | None = None,
) -> ValidationResult:
    return ValidationResult(
        halt=TypedHalt(
            code=code,
            stage=stage,
            field_name=field_name,
            expected=expected,
            observed=observed,
        )
    )


# ---------------------------------------------------------------------------
# Step: structural / duplicate-reference ambiguity check.
# ---------------------------------------------------------------------------


def _check_configuration_shape(
    config: NonSecretConfigurationInput,
) -> ValidationResult | None:
    seen_kinds: set[CredentialReferenceKind] = set()
    for reference in config.credential_references:
        if reference.kind in seen_kinds:
            return _halt(
                HaltCode.CONFIGURATION_AMBIGUOUS,
                ValidationStage.NON_SECRET_PARSED,
                field_name="credential_references",
                expected="at most one reference per credential kind",
                observed="duplicate credential reference kind",
            )
        seen_kinds.add(reference.kind)
    return None


# ---------------------------------------------------------------------------
# Step: environment validation.
# ---------------------------------------------------------------------------


def _validate_environment(
    config: NonSecretConfigurationInput,
) -> tuple[Environment, None] | tuple[None, ValidationResult]:
    raw = config.environment

    if raw is None or raw == "" or raw == Environment.UNSET.value:
        return None, _halt(
            HaltCode.ENVIRONMENT_UNSET,
            ValidationStage.NON_SECRET_PARSED,
            field_name=config.environment_source_field,
            expected="KALSHI_DEMO",
            observed="unset",
        )

    if raw not in _ENVIRONMENT_VALUES:
        return None, _halt(
            HaltCode.ENVIRONMENT_UNKNOWN,
            ValidationStage.NON_SECRET_PARSED,
            field_name=config.environment_source_field,
            expected="KALSHI_DEMO",
            observed="unrecognized_token",
        )

    environment = Environment(raw)

    if environment is Environment.KALSHI_PRODUCTION:
        return None, _halt(
            HaltCode.PRODUCTION_ACCESS_PROHIBITED,
            ValidationStage.NON_SECRET_PARSED,
            field_name=config.environment_source_field,
            expected="KALSHI_DEMO",
            observed="KALSHI_PRODUCTION",
        )

    if environment is not Environment.KALSHI_DEMO:
        # Unreachable with the current closed Environment enum (only
        # UNSET, KALSHI_DEMO, and KALSHI_PRODUCTION exist), retained for
        # exact conformance with Candidate 02 Section 20.1's
        # ENVIRONMENT_NOT_AUTHORIZED semantics for a future recognized
        # non-Demo, non-production environment value.
        return None, _halt(
            HaltCode.ENVIRONMENT_NOT_AUTHORIZED,
            ValidationStage.NON_SECRET_PARSED,
            field_name=config.environment_source_field,
            expected="KALSHI_DEMO",
            observed="recognized_unauthorized_environment",
        )

    return environment, None


# ---------------------------------------------------------------------------
# Step: endpoint validation.
# ---------------------------------------------------------------------------

_UNSAFE_CHARACTERS = frozenset(" \t\r\n")


def _has_control_characters(raw: str) -> bool:
    return any(ord(char) < 0x20 or ord(char) == 0x7F for char in raw)


def _has_dot_segment_or_encoded_separator(path: str) -> bool:
    if "//" in path:
        return True
    segments = path.split("/")
    if "." in segments or ".." in segments:
        return True
    lowered = path.lower()
    if "%2f" in lowered or "%2e%2e" in lowered or "%5c" in lowered:
        return True
    return False


def _validate_one_endpoint(
    raw_url: str,
    *,
    surface_name: str,
    required_scheme: str,
    required_path: str,
    demo_host: str,
    production_host: str,
    stage: ValidationStage,
) -> tuple[EndpointComponents, None] | tuple[None, ValidationResult]:
    if raw_url is None or raw_url == "":
        return None, _halt(
            HaltCode.ENDPOINT_MISSING,
            stage,
            field_name=surface_name,
            expected="non-blank URL",
            observed="missing",
        )

    if _has_control_characters(raw_url) or any(
        char in _UNSAFE_CHARACTERS for char in raw_url
    ):
        return None, _halt(
            HaltCode.ENDPOINT_MALFORMED,
            stage,
            field_name=surface_name,
            expected="URL with no whitespace or control characters",
            observed="whitespace_or_control_characters",
        )

    try:
        parts: SplitResult = urlsplit(raw_url)
    except ValueError:
        return None, _halt(
            HaltCode.ENDPOINT_MALFORMED,
            stage,
            field_name=surface_name,
            expected="parseable absolute URL",
            observed="unparseable",
        )

    if not parts.scheme or not parts.netloc:
        return None, _halt(
            HaltCode.ENDPOINT_MALFORMED,
            stage,
            field_name=surface_name,
            expected="absolute URL with scheme and host",
            observed="relative_or_opaque_url",
        )

    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        return None, _halt(
            HaltCode.ENDPOINT_MALFORMED,
            stage,
            field_name=surface_name,
            expected="no user information",
            observed="user_info_present",
        )

    if parts.query:
        return None, _halt(
            HaltCode.ENDPOINT_MALFORMED,
            stage,
            field_name=surface_name,
            expected="no query string",
            observed="query_present",
        )

    if parts.fragment:
        return None, _halt(
            HaltCode.ENDPOINT_MALFORMED,
            stage,
            field_name=surface_name,
            expected="no fragment",
            observed="fragment_present",
        )

    if not parts.hostname:
        return None, _halt(
            HaltCode.ENDPOINT_MALFORMED,
            stage,
            field_name=surface_name,
            expected="non-empty host",
            observed="empty_host",
        )

    path = parts.path
    if _has_dot_segment_or_encoded_separator(path):
        return None, _halt(
            HaltCode.ENDPOINT_MALFORMED,
            stage,
            field_name=surface_name,
            expected="path with no dot-segments or encoded separators",
            observed="unsafe_path_encoding",
        )

    try:
        raw_port = parts.port
    except ValueError:
        return None, _halt(
            HaltCode.ENDPOINT_MALFORMED,
            stage,
            field_name=surface_name,
            expected="valid numeric port",
            observed="malformed_port",
        )

    if parts.scheme != required_scheme:
        return None, _halt(
            HaltCode.ENDPOINT_SCHEME_PROHIBITED,
            stage,
            field_name=surface_name,
            expected=required_scheme,
            observed="other_scheme",
        )

    effective_port = raw_port if raw_port is not None else _DEFAULT_PORT_BY_SCHEME[required_scheme]
    if effective_port != _ALLOWED_PORT:
        return None, _halt(
            HaltCode.ENDPOINT_PORT_PROHIBITED,
            stage,
            field_name=surface_name,
            expected=str(_ALLOWED_PORT),
            observed="other_port",
        )

    if path != required_path:
        return None, _halt(
            HaltCode.ENDPOINT_PATH_PROHIBITED,
            stage,
            field_name=surface_name,
            expected=required_path,
            observed="other_path",
        )

    hostname = parts.hostname.lower()

    if hostname == production_host:
        return None, _halt(
            HaltCode.ENVIRONMENT_ENDPOINT_MISMATCH,
            stage,
            field_name=surface_name,
            expected=demo_host,
            observed="production_host",
        )

    if hostname != demo_host:
        return None, _halt(
            HaltCode.ENDPOINT_HOST_PROHIBITED,
            stage,
            field_name=surface_name,
            expected=demo_host,
            observed="other_host",
        )

    components = EndpointComponents(
        scheme=required_scheme,
        host=demo_host,
        port=_ALLOWED_PORT,
        path=required_path,
        has_user_info=False,
        has_query=False,
        has_fragment=False,
    )

    # Final exact-tuple safety net (Candidate 02 Section 20.1
    # ENDPOINT_NOT_ALLOWLISTED). Unreachable given the checks above, which
    # already enforce every component of the single allowed tuple.
    if components != (_DEMO_REST if surface_name == "rest_endpoint" else _DEMO_WEBSOCKET):
        return None, _halt(
            HaltCode.ENDPOINT_NOT_ALLOWLISTED,
            stage,
            field_name=surface_name,
            expected="exact allowlisted endpoint tuple",
            observed="other_tuple",
        )

    return components, None


def _validate_endpoints(
    config: NonSecretConfigurationInput,
) -> tuple[EndpointProfile, None] | tuple[None, ValidationResult]:
    rest, rest_halt = _validate_one_endpoint(
        config.rest_endpoint,
        surface_name="rest_endpoint",
        required_scheme="https",
        required_path=_DEMO_REST.path,
        demo_host=_DEMO_REST.host,
        production_host=_PRODUCTION_REST_HOST,
        stage=ValidationStage.ENVIRONMENT_VALIDATED,
    )
    if rest_halt is not None:
        return None, rest_halt

    websocket, ws_halt = _validate_one_endpoint(
        config.websocket_endpoint,
        surface_name="websocket_endpoint",
        required_scheme="wss",
        required_path=_DEMO_WEBSOCKET.path,
        demo_host=_DEMO_WEBSOCKET.host,
        production_host=_PRODUCTION_WEBSOCKET_HOST,
        stage=ValidationStage.ENVIRONMENT_VALIDATED,
    )
    if ws_halt is not None:
        return None, ws_halt

    assert rest is not None and websocket is not None
    return (
        EndpointProfile(
            environment=Environment.KALSHI_DEMO,
            rest=rest,
            websocket=websocket,
            allowlist_revision=config.endpoint_allowlist_revision,
        ),
        None,
    )


# ---------------------------------------------------------------------------
# Step: capability-envelope trust boundary.
# ---------------------------------------------------------------------------


def _validate_capability_envelope_fields(
    config: NonSecretConfigurationInput,
) -> ValidationResult | None:
    """Public consumption boundary for the capability envelope.

    Delegates entirely to the shared gate in `models`, which enforces the
    exact runtime type and revalidates the complete field invariant from
    the envelope's current values. Every failure maps to the existing safe
    `CAPABILITY_FIELD_MISSING` halt with fixed, non-secret classification
    metadata; the underlying exception's message is never propagated.
    """

    try:
        require_usable_capability_envelope(config.capability_envelope)
    except CapabilityEnvelopeError:
        return _halt(
            HaltCode.CAPABILITY_FIELD_MISSING,
            ValidationStage.ENDPOINT_PROFILE_VALIDATED,
            field_name="capability_envelope",
            expected="complete valid TaskAuthorizationCapabilityEnvelope",
            observed="missing_or_invalid",
        )
    return None


# ---------------------------------------------------------------------------
# Step: requested-capability validation and effective-capability computation.
# ---------------------------------------------------------------------------


def _validate_requested_capability(
    config: NonSecretConfigurationInput,
) -> tuple[RequestedCapability, None] | tuple[None, ValidationResult]:
    raw = config.requested_capability
    envelope = config.capability_envelope

    if raw not in _REQUESTED_CAPABILITY_VALUES:
        return None, _halt(
            HaltCode.CAPABILITY_FIELD_MISSING,
            ValidationStage.CAPABILITY_ENVELOPE_VALIDATED,
            field_name="requested_capability",
            expected="one closed RequestedCapability value",
            observed="unrecognized_token",
        )

    requested = RequestedCapability(raw)

    if requested in _PRODUCTION_REQUESTED_CAPABILITIES:
        return None, _halt(
            HaltCode.PRODUCTION_ACCESS_PROHIBITED,
            ValidationStage.CAPABILITY_ENVELOPE_VALIDATED,
            field_name="requested_capability",
            expected="a Demo capability",
            observed="production_capability",
        )

    if requested is RequestedCapability.DEMO_WRITE:
        return None, _halt(
            HaltCode.WRITE_CAPABILITY_PROHIBITED,
            ValidationStage.CAPABILITY_ENVELOPE_VALIDATED,
            field_name="requested_capability",
            expected="DEMO_PUBLIC_REST_READ or DEMO_AUTHENTICATED_READ",
            observed="DEMO_WRITE",
        )

    if requested is RequestedCapability.DEMO_PUBLIC_REST_READ:
        if (
            envelope.demo_public_reads is not AuthorizationValue.PERMITTED
            or envelope.credential_use is not AuthorizationValue.PROHIBITED
        ):
            return None, _halt(
                HaltCode.CAPABILITY_NOT_AUTHORIZED,
                ValidationStage.CAPABILITY_ENVELOPE_VALIDATED,
                field_name="requested_capability",
                expected="demo_public_reads=PERMITTED, credential_use=PROHIBITED",
                observed="not_authorized",
            )
        return requested, None

    if requested is RequestedCapability.DEMO_AUTHENTICATED_READ:
        if (
            envelope.demo_authenticated_reads is not AuthorizationValue.PERMITTED
            or envelope.credential_use is not AuthorizationValue.PERMITTED
        ):
            return None, _halt(
                HaltCode.CAPABILITY_NOT_AUTHORIZED,
                ValidationStage.CAPABILITY_ENVELOPE_VALIDATED,
                field_name="requested_capability",
                expected="demo_authenticated_reads=PERMITTED, credential_use=PERMITTED",
                observed="not_authorized",
            )
        return requested, None

    # Unreachable: every RequestedCapability member is handled above.
    return None, _halt(
        HaltCode.CAPABILITY_NOT_AUTHORIZED,
        ValidationStage.CAPABILITY_ENVELOPE_VALIDATED,
        field_name="requested_capability",
        expected="a supported Demo capability",
        observed="unsupported",
    )


# ---------------------------------------------------------------------------
# Step: credential source-name validation. Values are never read.
# ---------------------------------------------------------------------------


def _validate_credentials(
    requested: RequestedCapability,
    references: tuple[CredentialSourceReference, ...],
) -> (
    tuple[tuple[tuple[CredentialReferenceKind, CredentialReferenceState], ...], None]
    | tuple[None, ValidationResult]
):
    if requested is RequestedCapability.DEMO_PUBLIC_REST_READ:
        if references:
            return None, _halt(
                HaltCode.CONFIGURATION_AMBIGUOUS,
                ValidationStage.REQUESTED_CAPABILITY_VALIDATED,
                field_name="credential_references",
                expected="no credential references for a public-only capability",
                observed="credential_references_present",
            )
        return (
            tuple(
                (kind, CredentialReferenceState.NOT_REQUIRED)
                for kind in _REQUIRED_CREDENTIAL_KINDS
            ),
            None,
        )

    assert requested is RequestedCapability.DEMO_AUTHENTICATED_READ

    by_kind = {reference.kind: reference for reference in references}

    # Namespace check first (highest precedence among credential checks):
    # every supplied reference must use the exact accepted Demo source
    # name for its declared kind.
    for reference in references:
        expected_name = _ACCEPTED_CREDENTIAL_SOURCE_NAMES.get(reference.kind)
        if expected_name is None or reference.source_name != expected_name:
            return None, _halt(
                HaltCode.CREDENTIAL_NAMESPACE_MISMATCH,
                ValidationStage.REQUESTED_CAPABILITY_VALIDATED,
                field_name="credential_references",
                expected="KALSHI_DEMO_API_KEY_ID / KALSHI_DEMO_PRIVATE_KEY_PEM",
                observed="other_source_name",
            )

    # Missing check: both exact kinds must be present.
    for kind in _REQUIRED_CREDENTIAL_KINDS:
        reference = by_kind.get(kind)
        if reference is None or reference.state is CredentialReferenceState.MISSING:
            return None, _halt(
                HaltCode.CREDENTIAL_REFERENCE_MISSING,
                ValidationStage.REQUESTED_CAPABILITY_VALIDATED,
                field_name=kind.value,
                expected="CONFIGURED",
                observed="missing",
            )

    # Placeholder check: neither reference may be a placeholder.
    for kind in _REQUIRED_CREDENTIAL_KINDS:
        reference = by_kind[kind]
        if reference.state is CredentialReferenceState.PLACEHOLDER:
            return None, _halt(
                HaltCode.CREDENTIAL_PLACEHOLDER,
                ValidationStage.REQUESTED_CAPABILITY_VALIDATED,
                field_name=kind.value,
                expected="CONFIGURED",
                observed="placeholder",
            )
        if reference.state is not CredentialReferenceState.CONFIGURED:
            return None, _halt(
                HaltCode.CREDENTIAL_NAMESPACE_MISMATCH,
                ValidationStage.REQUESTED_CAPABILITY_VALIDATED,
                field_name=kind.value,
                expected="CONFIGURED",
                observed="unrecognized_state",
            )

    return (
        tuple(
            (kind, CredentialReferenceState.CONFIGURED)
            for kind in _REQUIRED_CREDENTIAL_KINDS
        ),
        None,
    )


# ---------------------------------------------------------------------------
# Orchestration.
# ---------------------------------------------------------------------------


def validate(config: NonSecretConfigurationInput) -> ValidationResult:
    """Run the complete deterministic validation sequence
    (Candidate 02 Section 18.1) and produce exactly one `ValidationResult`.

    Stops at the first primary halt. Never constructs a transport, signer,
    credential object, or partial profile. Never performs network or file
    I/O and never reads an environment variable.
    """

    shape_halt = _check_configuration_shape(config)
    if shape_halt is not None:
        return shape_halt

    environment, env_halt = _validate_environment(config)
    if env_halt is not None:
        return env_halt
    assert environment is Environment.KALSHI_DEMO

    endpoint_profile, endpoint_halt = _validate_endpoints(config)
    if endpoint_halt is not None:
        return endpoint_halt
    assert endpoint_profile is not None

    envelope_halt = _validate_capability_envelope_fields(config)
    if envelope_halt is not None:
        return envelope_halt

    requested, capability_halt = _validate_requested_capability(config)
    if capability_halt is not None:
        return capability_halt
    assert requested is not None

    credential_states, credential_halt = _validate_credentials(
        requested, config.credential_references
    )
    if credential_halt is not None:
        return credential_halt
    assert credential_states is not None

    profile = ValidatedDemoProfile(
        environment=Environment.KALSHI_DEMO,
        rest=endpoint_profile.rest,
        websocket=endpoint_profile.websocket,
        requested_capability=requested,
        effective_capability=requested,
        credential_reference_states=credential_states,
        allowlist_revision=endpoint_profile.allowlist_revision,
        validation_schema_revision=config.config_schema_revision,
    )
    return ValidationResult(success=profile)
