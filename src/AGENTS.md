# ARB Source-Code Instructions

This file applies to `src/` and all descendants. Root `AGENTS.md` also applies.

## Source boundaries

- Modify only source paths explicitly writable in the active task.
- Do not add imports or helpers in adjacent modules unless those paths are authorized.
- Do not edit package exports or `__init__.py` unless explicitly authorized.
- Do not add dependencies unless explicitly authorized.

## Network and side effects

For offline implementation tasks:

- no module-owned real network I/O;
- no DNS/socket/HTTP client activity;
- no real environment-secret reads;
- no account access;
- no venue writes;
- no import-time network, credential, filesystem-secret, or execution side effects.

Where a venue boundary is required, prefer explicit caller-supplied/fakeable interfaces consistent
with the controlling specification.

## Exactness

- Use `Decimal` for exact monetary/quantity arithmetic where required.
- Preserve opaque identifiers exactly.
- Fail closed on malformed, ambiguous, stale, conflicting, or out-of-scope inputs when the
  controlling contract requires it.
- Do not fabricate venue fields or infer unsupported economic facts.

## Capability design

For safety-critical adapters, prefer structural capability restriction over comments or convention.

Examples:

- fixed operation/method surfaces instead of arbitrary HTTP method parameters;
- exact route enums/builders instead of arbitrary URLs;
- explicit Demo/production separation;
- typed result/failure classifications;
- bounded retries, redirects, pagination, and deadlines.

The controlling task specification is authoritative where it is more specific.
