"""Kalshi Demo offline environment and capability-envelope validator.

This package is a pure, offline, non-secret static validator. It performs
no DNS resolution, no socket or HTTP/WebSocket activity, no credential
reads, no private-key parsing, and no signing. It constructs no transport,
signer, or venue client of any kind.

Scope is limited to the exact behavior authorized by the accepted
specification `SPEC_kalshi_demo_environment_separation_and_capability_envelope.md`
(Candidate 02), the controlling implementation handoff
`MARCO_HANDOFF_KALSHI_DEMO_OFFLINE_VALIDATOR_IMPLEMENTATION_01.md`, the
Implementation 02 bounded-correction dispatch plus its runtime amendment,
the Implementation 03 correction (canonical, ASCII-only `issue_date`
format), the Implementation 04 correction (exact built-in `str` type for
`issue_date`), and the Implementation 05 correction for task
`KALSHI_DEMO_ENVIRONMENT_SEPARATION_OFFLINE_VALIDATOR_IMPLEMENTATION_05`
(one shared capability-envelope invariant enforced at construction *and*
re-enforced at every public consumption boundary, with an exact runtime
type gate).
"""

from __future__ import annotations

from .errors import HaltCode, TypedHalt
from .models import (
    CAPABILITY_ENVELOPE_FIELDS,
    CAPABILITY_ENVELOPE_METADATA_FIELDS,
    AuthorizationValue,
    CapabilityEnvelopeError,
    CapabilityEnvelopeTypeError,
    CredentialReferenceKind,
    CredentialReferenceState,
    CredentialSourceReference,
    DuplicateCapabilityKeyError,
    EndpointComponents,
    EndpointProfile,
    Environment,
    InvalidCapabilityValueError,
    MissingCapabilityFieldError,
    NonFiniteCapabilityValueError,
    NonSecretConfigurationInput,
    RequestedCapability,
    TaskAuthorizationCapabilityEnvelope,
    UnknownCapabilityFieldError,
    ValidatedDemoProfile,
    ValidationResult,
    ValidationStage,
    check_capability_envelope_fields,
    require_usable_capability_envelope,
)
from .validation import validate

__all__ = [
    "CAPABILITY_ENVELOPE_FIELDS",
    "CAPABILITY_ENVELOPE_METADATA_FIELDS",
    "AuthorizationValue",
    "CapabilityEnvelopeError",
    "CapabilityEnvelopeTypeError",
    "CredentialReferenceKind",
    "CredentialReferenceState",
    "CredentialSourceReference",
    "DuplicateCapabilityKeyError",
    "EndpointComponents",
    "EndpointProfile",
    "Environment",
    "HaltCode",
    "InvalidCapabilityValueError",
    "MissingCapabilityFieldError",
    "NonFiniteCapabilityValueError",
    "NonSecretConfigurationInput",
    "RequestedCapability",
    "TaskAuthorizationCapabilityEnvelope",
    "TypedHalt",
    "UnknownCapabilityFieldError",
    "ValidatedDemoProfile",
    "ValidationResult",
    "ValidationStage",
    "check_capability_envelope_fields",
    "require_usable_capability_envelope",
    "validate",
]
