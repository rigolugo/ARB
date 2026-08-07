"""Closed enums and immutable, non-secret data records for the Kalshi Demo
offline environment and capability-envelope validator.

Nothing in this module reads environment variables, opens files, performs
network I/O, or stores credential values. `CredentialSourceReference`
carries only an opaque, non-secret source name (an environment-variable
*name*, never its value) and a non-secret state classification supplied by
the caller; its `source_name` is never exposed through `repr()` or
`str()`, whether rendered directly or nested inside a containing object.

Capability-envelope trust boundary (Implementation 05)
-----------------------------------------------------

There is exactly one implementation of the capability-envelope invariant,
`check_capability_envelope_fields`, and exactly one consumption-boundary
gate, `require_usable_capability_envelope`. Both live here, and every
consumer -- dataclass construction, `validate()`, canonical
serialization, and identity generation -- routes through them. No module
keeps its own copy of the envelope rules, so the rules cannot drift
between call sites.

Successful prior `__post_init__` execution is never treated as evidence
that an envelope is *currently* valid:

* `__post_init__` checks the field invariant at construction time.
* Every public consumption boundary re-checks the same invariant against
  the envelope's *current* field values, so an envelope mutated after
  construction (including via `object.__setattr__`, which bypasses the
  frozen-dataclass guard) fails at use time.
* Consumption boundaries additionally require exact runtime type
  `TaskAuthorizationCapabilityEnvelope`, rejecting duck-typed
  look-alikes, proxies, wrappers, and subclasses -- including a subclass
  that suppresses or overrides `__post_init__` to skip construction-time
  validation.

Field-level type rules use exact built-in types rather than `isinstance`,
so no subclass can override a protocol method (`__getitem__`, `__eq__`,
`__index__`, `strip`, and so on) to present different content to
different call sites:

* `schema_version` -- `type(value) is int` (excludes `bool` and every
  `int` subclass) and equal to exactly `1`.
* `authorization_id`, `authorizing_authority`, `task_id`,
  `completion_rule` -- `type(value) is str`, checked *before* any string
  method such as `strip()` is called, then nonblank.
* `issue_date` -- `type(value) is str`, then an ASCII-only, fully
  anchored `[0-9]{4}-[0-9]{2}-[0-9]{2}` match via `re.fullmatch`, then a
  real Gregorian calendar date. `\\d` is deliberately not used (it matches
  full-width and Arabic-Indic digit forms) and `fullmatch` is
  deliberately used instead of `match()` plus `$` (which would tolerate a
  terminal newline).
* the thirteen authorization fields -- `type(value) is AuthorizationValue`.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field
from datetime import date as _date
from typing import TYPE_CHECKING, Optional, Tuple

if TYPE_CHECKING:
    # Import only for type checkers. Avoids a runtime circular import with
    # errors.py, which imports ValidationStage from this module.
    from .errors import TypedHalt


class Environment(enum.StrEnum):
    """Closed set of environment values. No default exists."""

    UNSET = "UNSET"
    KALSHI_DEMO = "KALSHI_DEMO"
    KALSHI_PRODUCTION = "KALSHI_PRODUCTION"


class RequestedCapability(enum.StrEnum):
    """Closed set of capabilities a caller may request for later
    construction. Only the two Demo read capabilities can validate
    successfully in this offline package."""

    DEMO_PUBLIC_REST_READ = "DEMO_PUBLIC_REST_READ"
    DEMO_AUTHENTICATED_READ = "DEMO_AUTHENTICATED_READ"
    DEMO_WRITE = "DEMO_WRITE"
    PRODUCTION_PUBLIC_REST_READ = "PRODUCTION_PUBLIC_REST_READ"
    PRODUCTION_AUTHENTICATED_READ = "PRODUCTION_AUTHENTICATED_READ"
    PRODUCTION_WRITE = "PRODUCTION_WRITE"


class AuthorizationValue(enum.StrEnum):
    """Closed set of task-authorization values. No boolean form is
    permitted anywhere in this package."""

    PERMITTED = "PERMITTED"
    PROHIBITED = "PROHIBITED"


class CredentialReferenceKind(enum.StrEnum):
    """Closed set of non-secret credential *source* classifications.
    These name where a value would come from later; they never carry the
    value itself."""

    API_KEY_ID_ENV_SOURCE = "API_KEY_ID_ENV_SOURCE"
    PRIVATE_KEY_PEM_ENV_SOURCE = "PRIVATE_KEY_PEM_ENV_SOURCE"


class CredentialReferenceState(enum.StrEnum):
    """Closed set of non-secret presence states for a credential source
    reference. The validator never reads the underlying value; this state
    is supplied non-secretly by the caller."""

    CONFIGURED = "CONFIGURED"
    MISSING = "MISSING"
    PLACEHOLDER = "PLACEHOLDER"
    NOT_REQUIRED = "NOT_REQUIRED"


class ValidationStage(enum.StrEnum):
    """Deterministic validation state machine stages (Candidate 02
    Section 18.2)."""

    RAW_NON_SECRET_INPUT = "RAW_NON_SECRET_INPUT"
    NON_SECRET_PARSED = "NON_SECRET_PARSED"
    ENVIRONMENT_VALIDATED = "ENVIRONMENT_VALIDATED"
    ENDPOINT_PROFILE_VALIDATED = "ENDPOINT_PROFILE_VALIDATED"
    CAPABILITY_ENVELOPE_VALIDATED = "CAPABILITY_ENVELOPE_VALIDATED"
    REQUESTED_CAPABILITY_VALIDATED = "REQUESTED_CAPABILITY_VALIDATED"
    CREDENTIAL_REFERENCES_VALIDATED = "CREDENTIAL_REFERENCES_VALIDATED"
    REDACTION_POLICY_ESTABLISHED = "REDACTION_POLICY_ESTABLISHED"
    VALIDATED_DEMO_PROFILE = "VALIDATED_DEMO_PROFILE"
    HALTED_NO_PROFILE = "HALTED_NO_PROFILE"


# The thirteen required capability-envelope fields (Candidate 02 Section 16.1).
CAPABILITY_ENVELOPE_FIELDS: Tuple[str, ...] = (
    "network_access",
    "demo_public_reads",
    "demo_authenticated_reads",
    "demo_writes",
    "production_public_reads",
    "production_authenticated_reads",
    "production_writes",
    "credential_use",
    "account_funding",
    "code_changes",
    "tests",
    "artifact_generation",
    "repository_commits",
)

# The four required non-blank string metadata fields, excluding
# issue_date, which has its own canonical-calendar-date rule.
CAPABILITY_ENVELOPE_METADATA_FIELDS: Tuple[str, ...] = (
    "authorization_id",
    "authorizing_authority",
    "task_id",
    "completion_rule",
)

_SCHEMA_VERSION = 1

# ASCII-only digits, fully anchored via re.fullmatch. Deliberately NOT
# `\d` (which matches any Unicode decimal digit, including full-width and
# Arabic-Indic forms) and deliberately matched with `fullmatch` rather
# than `match(...)` plus a trailing `$` (which would tolerate a terminal
# newline).
_ISSUE_DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")

# Sentinel distinguishing "attribute absent" from "attribute is None".
_MISSING = object()


class CapabilityEnvelopeError(ValueError):
    """Base class for capability-envelope validation failures, whether
    raised while parsing JSON, while directly constructing a
    `TaskAuthorizationCapabilityEnvelope`, or while consuming one at a
    public boundary. Never carries a secret value; messages describe only
    field names and structural facts."""


class DuplicateCapabilityKeyError(CapabilityEnvelopeError):
    """Raised when the raw capability-envelope JSON object contains a
    duplicate key."""


class UnknownCapabilityFieldError(CapabilityEnvelopeError):
    """Raised when the raw capability-envelope JSON object contains a
    field outside the exact required schema."""


class MissingCapabilityFieldError(CapabilityEnvelopeError):
    """Raised when the raw capability-envelope JSON object omits a
    required field, or when a consumed envelope lacks a required
    attribute entirely."""


class InvalidCapabilityValueError(CapabilityEnvelopeError):
    """Raised when a capability-envelope field has the wrong type, an
    invalid value, or a non-enumerated authorization value — whether the
    envelope originated from JSON parsing, direct object construction, or
    was mutated after construction."""


class NonFiniteCapabilityValueError(CapabilityEnvelopeError):
    """Raised when the raw capability-envelope JSON contains a
    floating-point number, `NaN`, or an infinity."""


class CapabilityEnvelopeTypeError(CapabilityEnvelopeError):
    """Raised when an object presented at a public consumption boundary is
    not of exact runtime type `TaskAuthorizationCapabilityEnvelope` —
    covering duck-typed look-alikes, proxies, wrappers, and subclasses
    (including subclasses that suppress or override `__post_init__`)."""


def _is_blank_string(value: object) -> bool:
    """Deterministic blank rule. The caller must already have confirmed
    exact `str` type; this never calls a string method on a
    non-exact-`str` object."""

    return value.strip() == ""


def _check_schema_version(value: object) -> None:
    # `type(value) is int` excludes bool (a subclass of int) and every
    # other int subclass, including one overriding __eq__ or __index__.
    if type(value) is not int or value != _SCHEMA_VERSION:
        raise InvalidCapabilityValueError(
            f"schema_version must be exactly the built-in int {_SCHEMA_VERSION}"
        )


def _check_metadata_string(name: str, value: object) -> None:
    # Exact-type gate first, short-circuited via `or`, so strip() is never
    # invoked on a str subclass that could override it.
    if type(value) is not str or _is_blank_string(value):
        raise InvalidCapabilityValueError(
            f"{name} must be a non-blank built-in str"
        )


def _check_issue_date(value: object) -> None:
    # Exact-type gate first, short-circuited via `or`, so neither the
    # regex nor the slicing below ever runs on a str subclass.
    if type(value) is not str or _ISSUE_DATE_PATTERN.fullmatch(value) is None:
        raise InvalidCapabilityValueError(
            "issue_date must be an exact built-in str, ASCII canonical YYYY-MM-DD"
        )
    year, month, day = int(value[0:4]), int(value[5:7]), int(value[8:10])
    try:
        _date(year, month, day)
    except ValueError:
        raise InvalidCapabilityValueError(
            "issue_date must represent a real calendar date"
        ) from None


def _check_authorization_value(name: str, value: object) -> None:
    if type(value) is not AuthorizationValue:
        raise InvalidCapabilityValueError(
            f"{name} must be exactly an AuthorizationValue member"
        )


def check_capability_envelope_fields(envelope: object) -> None:
    """The single, shared capability-envelope field invariant.

    Reads the object's *current* attribute values and raises a
    `CapabilityEnvelopeError` subclass if any rule is violated. Performs
    no type check on the container itself, so it is usable both from
    `TaskAuthorizationCapabilityEnvelope.__post_init__` (where the
    instance is mid-construction) and from consumption boundaries after
    `require_usable_capability_envelope` has applied the exact-type gate.

    Raises only this module's capability-envelope exceptions; no raw
    third-party or arbitrary exception content escapes.
    """

    for name in ("schema_version",) + CAPABILITY_ENVELOPE_METADATA_FIELDS + (
        "issue_date",
    ) + CAPABILITY_ENVELOPE_FIELDS:
        if getattr(envelope, name, _MISSING) is _MISSING:
            raise MissingCapabilityFieldError(
                f"capability envelope is missing required field: {name}"
            )

    _check_schema_version(envelope.schema_version)

    for name in CAPABILITY_ENVELOPE_METADATA_FIELDS:
        _check_metadata_string(name, getattr(envelope, name))

    _check_issue_date(envelope.issue_date)

    for name in CAPABILITY_ENVELOPE_FIELDS:
        _check_authorization_value(name, getattr(envelope, name))


def require_usable_capability_envelope(envelope: object) -> None:
    """The single, shared consumption-boundary gate.

    Requires exact runtime type `TaskAuthorizationCapabilityEnvelope`
    (rejecting duck-typed look-alikes, proxies, wrappers, and every
    subclass), then revalidates the complete field invariant from the
    envelope's current values. Prior successful construction is never
    accepted as evidence of current validity.
    """

    if type(envelope) is not TaskAuthorizationCapabilityEnvelope:
        raise CapabilityEnvelopeTypeError(
            "capability envelope must have exact type "
            "TaskAuthorizationCapabilityEnvelope"
        )
    check_capability_envelope_fields(envelope)


@dataclass(frozen=True, slots=True)
class TaskAuthorizationCapabilityEnvelope:
    """The complete, explicit task-authorization envelope. Every
    authorization field is exactly `PERMITTED` or `PROHIBITED`; nothing is
    inherited, defaulted, or implied.

    `__post_init__` applies the shared field invariant, so an invalid
    envelope cannot be constructed via any public route — JSON parsing or
    direct construction alike. Consumption boundaries independently
    re-apply that same invariant plus an exact-type gate, so neither a
    subclass that skips `__post_init__` nor an instance mutated after
    construction can be used.
    """

    schema_version: int
    authorization_id: str
    authorizing_authority: str
    task_id: str
    issue_date: str
    completion_rule: str
    network_access: AuthorizationValue
    demo_public_reads: AuthorizationValue
    demo_authenticated_reads: AuthorizationValue
    demo_writes: AuthorizationValue
    production_public_reads: AuthorizationValue
    production_authenticated_reads: AuthorizationValue
    production_writes: AuthorizationValue
    credential_use: AuthorizationValue
    account_funding: AuthorizationValue
    code_changes: AuthorizationValue
    tests: AuthorizationValue
    artifact_generation: AuthorizationValue
    repository_commits: AuthorizationValue

    def __post_init__(self) -> None:
        check_capability_envelope_fields(self)


@dataclass(frozen=True, slots=True, repr=False, eq=True)
class CredentialSourceReference:
    """A single opaque, non-secret credential source reference.

    `source_name` is an environment-variable *name* only (for example,
    `KALSHI_DEMO_API_KEY_ID`), never a value. `state` is supplied
    non-secretly by the caller and is never derived by reading the
    underlying value.

    `source_name` participates in equality but is deliberately excluded
    from `repr()` and `str()` — directly, and wherever this object is
    nested inside another record's default representation — so that no
    rendering path can leak it.
    """

    kind: CredentialReferenceKind
    source_name: str
    state: CredentialReferenceState

    def __repr__(self) -> str:
        return (
            "CredentialSourceReference("
            f"kind={self.kind.value}, state={self.state.value})"
        )

    def __str__(self) -> str:
        return self.__repr__()


@dataclass(frozen=True, slots=True)
class EndpointComponents:
    """One parsed, canonicalized URL's structural components. No DNS or
    network access is used to produce this."""

    scheme: str
    host: str
    port: int
    path: str
    has_user_info: bool
    has_query: bool
    has_fragment: bool


@dataclass(frozen=True, slots=True)
class EndpointProfile:
    """An immutable pair of parsed REST and WebSocket base endpoints bound
    to one explicit environment."""

    environment: Environment
    rest: EndpointComponents
    websocket: EndpointComponents
    allowlist_revision: str


@dataclass(frozen=True, slots=True)
class NonSecretConfigurationInput:
    """The complete non-secret input to one validation attempt. Contains
    no secret values. Its default representation never exposes a nested
    `CredentialSourceReference.source_name`, since that type's own
    `repr()`/`str()` already omit it."""

    environment: str
    environment_source_field: str
    rest_endpoint: str
    websocket_endpoint: str
    requested_capability: str
    capability_envelope: TaskAuthorizationCapabilityEnvelope
    config_schema_revision: int
    endpoint_allowlist_revision: str
    credential_references: Tuple[CredentialSourceReference, ...] = field(
        default_factory=tuple
    )


@dataclass(frozen=True, slots=True)
class ValidatedDemoProfile:
    """Immutable, non-secret proof that static configuration and task
    authorization passed validation. Not a client, credential object,
    transport, or venue evidence of any kind."""

    environment: Environment
    rest: EndpointComponents
    websocket: EndpointComponents
    requested_capability: RequestedCapability
    effective_capability: RequestedCapability
    credential_reference_states: Tuple[
        Tuple[CredentialReferenceKind, CredentialReferenceState], ...
    ]
    allowlist_revision: str
    validation_schema_revision: int
    secret_loaded: bool = False
    transport_constructed: bool = False
    network_request_sent: bool = False

    def __post_init__(self) -> None:
        if self.secret_loaded is not False:
            raise ValueError("ValidatedDemoProfile.secret_loaded must be False")
        if self.transport_constructed is not False:
            raise ValueError(
                "ValidatedDemoProfile.transport_constructed must be False"
            )
        if self.network_request_sent is not False:
            raise ValueError(
                "ValidatedDemoProfile.network_request_sent must be False"
            )


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """A disjoint validation result: exactly one of `success` or `halt`,
    never both, never neither."""

    success: Optional[ValidatedDemoProfile] = None
    halt: Optional["TypedHalt"] = None

    def __post_init__(self) -> None:
        if (self.success is None) == (self.halt is None):
            raise ValueError(
                "ValidationResult requires exactly one of success or halt"
            )
