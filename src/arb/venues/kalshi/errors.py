"""Typed halt codes and secret-safe halt records for the Kalshi Demo
offline validator (Candidate 02 Section 20)."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Optional, Tuple

from .models import (
    CapabilityEnvelopeError,
    CapabilityEnvelopeTypeError,
    DuplicateCapabilityKeyError,
    InvalidCapabilityValueError,
    MissingCapabilityFieldError,
    NonFiniteCapabilityValueError,
    UnknownCapabilityFieldError,
    ValidationStage,
)

# Re-exported here so callers can import capability-envelope exceptions
# from either `errors` or `models`. Defined in `models.py` (not here) so
# that the shared envelope invariant can raise them without creating a
# circular import between this module and `models.py`.
__all__ = [
    "HaltCode",
    "PRIMARY_PRECEDENCE",
    "TypedHalt",
    "CapabilityEnvelopeError",
    "CapabilityEnvelopeTypeError",
    "DuplicateCapabilityKeyError",
    "UnknownCapabilityFieldError",
    "MissingCapabilityFieldError",
    "InvalidCapabilityValueError",
    "NonFiniteCapabilityValueError",
]


class HaltCode(enum.StrEnum):
    """Required halt codes (Candidate 02 Section 20.1)."""

    CANONICAL_STATE_CONFLICT = "CANONICAL_STATE_CONFLICT"
    OFFICIAL_SOURCE_CONFLICT = "OFFICIAL_SOURCE_CONFLICT"
    CONFIGURATION_AMBIGUOUS = "CONFIGURATION_AMBIGUOUS"
    ENVIRONMENT_UNSET = "ENVIRONMENT_UNSET"
    ENVIRONMENT_UNKNOWN = "ENVIRONMENT_UNKNOWN"
    ENVIRONMENT_NOT_AUTHORIZED = "ENVIRONMENT_NOT_AUTHORIZED"
    ENDPOINT_MISSING = "ENDPOINT_MISSING"
    ENDPOINT_MALFORMED = "ENDPOINT_MALFORMED"
    ENDPOINT_SCHEME_PROHIBITED = "ENDPOINT_SCHEME_PROHIBITED"
    ENDPOINT_HOST_PROHIBITED = "ENDPOINT_HOST_PROHIBITED"
    ENDPOINT_PORT_PROHIBITED = "ENDPOINT_PORT_PROHIBITED"
    ENDPOINT_PATH_PROHIBITED = "ENDPOINT_PATH_PROHIBITED"
    ENDPOINT_NOT_ALLOWLISTED = "ENDPOINT_NOT_ALLOWLISTED"
    ENDPOINT_REDIRECT_PROHIBITED = "ENDPOINT_REDIRECT_PROHIBITED"
    ENVIRONMENT_ENDPOINT_MISMATCH = "ENVIRONMENT_ENDPOINT_MISMATCH"
    CREDENTIAL_NAMESPACE_MISMATCH = "CREDENTIAL_NAMESPACE_MISMATCH"
    CREDENTIAL_REFERENCE_MISSING = "CREDENTIAL_REFERENCE_MISSING"
    CREDENTIAL_PLACEHOLDER = "CREDENTIAL_PLACEHOLDER"
    CAPABILITY_FIELD_MISSING = "CAPABILITY_FIELD_MISSING"
    CAPABILITY_NOT_AUTHORIZED = "CAPABILITY_NOT_AUTHORIZED"
    PRODUCTION_ACCESS_PROHIBITED = "PRODUCTION_ACCESS_PROHIBITED"
    WRITE_CAPABILITY_PROHIBITED = "WRITE_CAPABILITY_PROHIBITED"
    SECRET_RENDERING_PROHIBITED = "SECRET_RENDERING_PROHIBITED"


# Primary precedence order (Candidate 02 Section 20.2). Index position is
# the tie-break rank; lower index wins when more than one code would apply.
PRIMARY_PRECEDENCE: Tuple[HaltCode, ...] = (
    HaltCode.CANONICAL_STATE_CONFLICT,
    HaltCode.OFFICIAL_SOURCE_CONFLICT,
    HaltCode.CONFIGURATION_AMBIGUOUS,
    HaltCode.ENVIRONMENT_UNSET,
    HaltCode.ENVIRONMENT_UNKNOWN,
    HaltCode.PRODUCTION_ACCESS_PROHIBITED,
    HaltCode.ENVIRONMENT_NOT_AUTHORIZED,
    HaltCode.ENDPOINT_MISSING,
    HaltCode.ENDPOINT_MALFORMED,
    HaltCode.ENDPOINT_SCHEME_PROHIBITED,
    HaltCode.ENDPOINT_PORT_PROHIBITED,
    HaltCode.ENDPOINT_PATH_PROHIBITED,
    HaltCode.ENVIRONMENT_ENDPOINT_MISMATCH,
    HaltCode.ENDPOINT_HOST_PROHIBITED,
    HaltCode.ENDPOINT_NOT_ALLOWLISTED,
    HaltCode.CAPABILITY_FIELD_MISSING,
    HaltCode.WRITE_CAPABILITY_PROHIBITED,
    HaltCode.CAPABILITY_NOT_AUTHORIZED,
    HaltCode.CREDENTIAL_NAMESPACE_MISMATCH,
    HaltCode.CREDENTIAL_REFERENCE_MISSING,
    HaltCode.CREDENTIAL_PLACEHOLDER,
    HaltCode.ENDPOINT_REDIRECT_PROHIBITED,
)


@dataclass(frozen=True, slots=True, repr=False, eq=True)
class TypedHalt:
    """A single, secret-safe, deterministic validation failure.

    Every field is a stable code, an enum, or a short safe classification
    string supplied by this package's own validation logic. No call site
    in this package ever places a credential value, PEM text, source
    name, or raw exception text into any field here.
    """

    code: HaltCode
    stage: ValidationStage
    field_name: Optional[str] = None
    expected: Optional[str] = None
    observed: Optional[str] = None
    contributing_codes: Tuple[HaltCode, ...] = field(default_factory=tuple)
    cause_code: Optional[HaltCode] = None

    def __str__(self) -> str:
        parts = [f"code={self.code.value}", f"stage={self.stage.value}"]
        if self.field_name is not None:
            parts.append(f"field_name={self.field_name}")
        if self.expected is not None:
            parts.append(f"expected={self.expected}")
        if self.observed is not None:
            parts.append(f"observed={self.observed}")
        if self.contributing_codes:
            parts.append(
                "contributing_codes="
                + ",".join(code.value for code in self.contributing_codes)
            )
        if self.cause_code is not None:
            parts.append(f"cause_code={self.cause_code.value}")
        return "TypedHalt(" + ", ".join(parts) + ")"

    def __repr__(self) -> str:
        return self.__str__()
