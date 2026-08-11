# ARB Test Instructions

This file applies to `tests/` and all descendants. Root `AGENTS.md` also applies.

## Offline safety

Unless the active task explicitly authorizes otherwise, tests must use:

- mocks;
- fakes;
- synthetic responses;
- synthetic account metadata;
- synthetic credentials/key material.

Tests must not perform:

- real DNS/socket/HTTP requests;
- Kalshi Demo requests;
- Kalshi production requests;
- Polymarket requests;
- real secret reads;
- account access;
- order CREATE/CANCEL/amend/decrease operations;
- funding or trading.

## Determinism

Control nondeterministic inputs when asserting byte-identical evidence or exact hashes.

Use deterministic:

- clocks;
- UUIDs/IDs;
- ordering;
- synthetic transport behavior;
- random seeds where randomness is required.

Do not compare two real-clock runs as byte-identical unless timing is intentionally excluded by the
controlling specification.

## Coverage

Tests should cover:

- accepted happy paths;
- malformed inputs;
- identity mismatches;
- capability/environment mismatches;
- deadline boundaries;
- retry/redirect bounds;
- pagination bounds where applicable;
- duplicate/conflicting records;
- exact Decimal/economic invariants;
- fail-closed behavior;
- secret-safe evidence.

Do not weaken or remove controlling assertions to make an implementation pass.

## Regression

Run the exact task-required test battery and full repository discovery when required.

Report exact pass/fail counts and any skipped tests.
