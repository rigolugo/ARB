"""Pure, offline, non-secret canonical serialization for the task
capability envelope.

No function in this module performs I/O, reads an environment variable,
or accepts an arbitrary Python object for serialization. Only the closed
`TaskAuthorizationCapabilityEnvelope` schema is ever produced or
consumed.

Structural JSON concerns (duplicate keys, unknown/missing fields,
non-finite numbers) are checked here, since they cannot be expressed as a
per-field dataclass rule. Every value-level rule -- `schema_version`,
metadata, canonical `issue_date`, and exact `AuthorizationValue`
membership -- lives in exactly one place,
`models.check_capability_envelope_fields`, so the JSON route and the
direct-construction route can never diverge. `json.loads` always produces
ordinary built-in `str` values for JSON strings, so the JSON-parsing
route automatically satisfies the exact-`str`-type requirements too.

`canonical_capability_envelope_bytes` and `capability_envelope_identity`
are public consumption boundaries: each calls
`models.require_usable_capability_envelope` first, so an envelope that is
the wrong exact type (duck-typed look-alike, proxy, wrapper, or
subclass), or that was mutated into an invalid state after construction,
produces neither canonical bytes nor an identity.
"""

from __future__ import annotations

import json
import hashlib
from typing import Any, Dict, List

from .models import (
    CAPABILITY_ENVELOPE_FIELDS,
    AuthorizationValue,
    DuplicateCapabilityKeyError,
    InvalidCapabilityValueError,
    MissingCapabilityFieldError,
    NonFiniteCapabilityValueError,
    TaskAuthorizationCapabilityEnvelope,
    UnknownCapabilityFieldError,
    require_usable_capability_envelope,
)

_META_FIELDS: tuple[str, ...] = (
    "authorization_id",
    "authorizing_authority",
    "task_id",
    "issue_date",
    "completion_rule",
)

_ALL_FIELDS: tuple[str, ...] = ("schema_version",) + _META_FIELDS + CAPABILITY_ENVELOPE_FIELDS


def _reject_non_finite_constant(constant: str) -> Any:
    raise NonFiniteCapabilityValueError(
        f"non-finite JSON constant is prohibited: {constant}"
    )


def _duplicate_key_object_pairs_hook(
    pairs: List[tuple[str, Any]]
) -> Dict[str, Any]:
    seen: set[str] = set()
    result: Dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise DuplicateCapabilityKeyError(f"duplicate key: {key}")
        seen.add(key)
        result[key] = value
    return result


def _reject_floats_recursive(value: Any) -> None:
    if isinstance(value, float):
        raise NonFiniteCapabilityValueError(
            "floating-point values are prohibited in the capability envelope"
        )
    if isinstance(value, dict):
        for nested in value.values():
            _reject_floats_recursive(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_floats_recursive(nested)


def parse_capability_envelope_json(
    text: str,
) -> TaskAuthorizationCapabilityEnvelope:
    """Parse one canonical capability-envelope JSON object.

    Rejects duplicate keys, unknown fields, missing fields, and any
    floating-point/NaN/infinity value anywhere in the structure. All
    remaining value-level rules are enforced by the shared invariant via
    the `TaskAuthorizationCapabilityEnvelope` constructor.
    """

    try:
        raw = json.loads(
            text,
            object_pairs_hook=_duplicate_key_object_pairs_hook,
            parse_constant=_reject_non_finite_constant,
        )
    except (DuplicateCapabilityKeyError, NonFiniteCapabilityValueError):
        raise
    except json.JSONDecodeError as exc:
        raise InvalidCapabilityValueError(f"invalid JSON: {exc}") from None

    if not isinstance(raw, dict):
        raise InvalidCapabilityValueError(
            "capability envelope must be a JSON object"
        )

    _reject_floats_recursive(raw)

    raw_keys = set(raw)
    allowed_keys = set(_ALL_FIELDS)

    unknown = raw_keys - allowed_keys
    if unknown:
        raise UnknownCapabilityFieldError(
            "unknown capability-envelope field(s): " + ", ".join(sorted(unknown))
        )

    missing = allowed_keys - raw_keys
    if missing:
        raise MissingCapabilityFieldError(
            "missing capability-envelope field(s): " + ", ".join(sorted(missing))
        )

    # Authorization fields must become actual AuthorizationValue instances
    # before construction: the shared invariant requires exact enum
    # membership and performs no coercion from a raw JSON string.
    permitted = AuthorizationValue.PERMITTED.value
    prohibited = AuthorizationValue.PROHIBITED.value
    capability_values: Dict[str, AuthorizationValue] = {}
    for name in CAPABILITY_ENVELOPE_FIELDS:
        value = raw[name]
        if value not in (permitted, prohibited):
            raise InvalidCapabilityValueError(
                f"{name} must be exactly PERMITTED or PROHIBITED"
            )
        capability_values[name] = AuthorizationValue(value)

    # schema_version and the five metadata fields are passed through
    # as-parsed; the shared invariant validates their type/shape/value.
    return TaskAuthorizationCapabilityEnvelope(
        schema_version=raw["schema_version"],
        authorization_id=raw["authorization_id"],
        authorizing_authority=raw["authorizing_authority"],
        task_id=raw["task_id"],
        issue_date=raw["issue_date"],
        completion_rule=raw["completion_rule"],
        **capability_values,
    )


def canonical_capability_envelope_bytes(
    envelope: TaskAuthorizationCapabilityEnvelope,
) -> bytes:
    """Produce deterministic canonical JSON bytes for one capability
    envelope: UTF-8, lexicographically sorted keys, `,`/`:` separators,
    no added whitespace.

    Public consumption boundary: the exact-type gate and the complete
    field invariant are revalidated against the envelope's current values
    before any bytes are produced.
    """

    require_usable_capability_envelope(envelope)

    obj: Dict[str, Any] = {
        "schema_version": envelope.schema_version,
        "authorization_id": envelope.authorization_id,
        "authorizing_authority": envelope.authorizing_authority,
        "task_id": envelope.task_id,
        "issue_date": envelope.issue_date,
        "completion_rule": envelope.completion_rule,
    }
    for name in CAPABILITY_ENVELOPE_FIELDS:
        obj[name] = getattr(envelope, name).value

    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def capability_envelope_identity(
    envelope: TaskAuthorizationCapabilityEnvelope,
) -> str:
    """Compute the deterministic `sha256:<hex>` identity of one capability
    envelope's canonical bytes.

    Public consumption boundary: revalidation happens via
    `canonical_capability_envelope_bytes`, so an invalid or wrong-typed
    envelope produces no identity.
    """

    digest = hashlib.sha256(canonical_capability_envelope_bytes(envelope)).hexdigest()
    return f"sha256:{digest}"
