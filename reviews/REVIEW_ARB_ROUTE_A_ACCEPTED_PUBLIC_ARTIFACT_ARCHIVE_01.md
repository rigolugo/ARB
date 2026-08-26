APPROVE

# REVIEW_ARB_ROUTE_A_ACCEPTED_PUBLIC_ARTIFACT_ARCHIVE_01

## Scope

Review of the user-uploaded lossless public Route-A archive for installation into the canonical repository. This review grants no runtime, venue, credential, persistence, writer-release, Gate-D, or production capability.

## Review source

User-upload review commit:

```text
commit = 74ae4d2cd9d00a98a76e12c07e217aefa357c264
message = ZIP UPLOAD
parent = 4106b805064ef704199810e32ffe2a3f3d7ecff7
tree = 8e4fb029161c70730327926cb366bd6ce0eb039e
```

The commit contains:

```text
ARB_ROUTE_A_ACCEPTED_PUBLIC_ARTIFACTS_2026_08_26.zip
raw_bytes = 213438
git_blob = de4794e55eed4210e9541b95e93d262926b83c02
```

The review commit itself is a review transport artifact, not a controlling technical specification.

## Exact archive identity

The independently held review ZIP has:

```text
raw_bytes = 213438
sha256 = 823ffab9cb048a010457c03efa2546a10c23413f561177cf93be49a1059fa222
computed_git_blob = de4794e55eed4210e9541b95e93d262926b83c02
```

The computed Git blob identity exactly equals the repository tree entry on the user-upload review commit. Therefore the repository object is byte-identical to the independently verified archive bytes.

Evidence classification:

```text
repository commit/tree/blob identity = INDEPENDENTLY_VERIFIED
local archive raw-byte/SHA identity = INDEPENDENTLY_VERIFIED
repository/local byte identity via Git blob equality = INDEPENDENTLY_VERIFIED
```

## Archive integrity

Static ZIP review:

```text
CRC = PASS
member_count = 10
missing_members = 0
extra_members = 0
member_byte_or_sha_mismatches = 0
```

Exact accepted members:

```text
KALSHI_DEMO_PERSISTENT_LEDGER_AND_RESTART_RECOVERY_SPEC_03.md
141566 bytes
98592d719db2dcb59bb5ade6f18700b9acf4ae1049480f409b60f228f1518ead

HANDOFF_KALSHI_DEMO_PERSISTENT_LEDGER_AND_RESTART_RECOVERY_SPEC_03.md
17942 bytes
43dd06f5a7d976bff54574f60298c7568f74e9c24b8f257e32306b45c8289b93

KALSHI_DEMO_EMERGENCY_CANCELLATION_AND_RISK_LIMITS_SPEC_03.md
183042 bytes
bb8f078185eb766ed1589441712d9cc6fcd77f574a1a2100a1901cfb75e9c8cb

HANDOFF_KALSHI_DEMO_EMERGENCY_CANCELLATION_AND_RISK_LIMITS_SPEC_03.md
19785 bytes
335048d61acd9367755629f90f584553ece7eed8553ffcf9c881a6feb4b944f3

KALSHI_DEMO_GATE_D_REAL_EXECUTION_SUBSTRATE_AND_WRITER_ELIGIBILITY_SPEC_01.md
68568 bytes
512000eea8db5562768682ae1659c03c20a2b5093fba68ef37eae784039a8336

HANDOFF_KALSHI_DEMO_GATE_D_REAL_EXECUTION_SUBSTRATE_AND_WRITER_ELIGIBILITY_SPEC_01.md
15390 bytes
57a37e444afcf0706adcc5f4f09bb280dc04c46a2fff8b4e678f6aead2dbaac8

KALSHI_DEMO_PRIMARY_DOMAIN_HISTORICAL_INCIDENT_RESOLUTION_READ_ONLY_SPEC_05.md
591027 bytes
5e51550edf3a644b07a640631564be4e53d248e7fa73c86f29e8fa15316457d6

HANDOFF_KALSHI_DEMO_PRIMARY_DOMAIN_HISTORICAL_INCIDENT_RESOLUTION_READ_ONLY_SPEC_05.md
12304 bytes
694d7a0bdb4af541b422a9ff617e7f2a2897987035a83c14b1e347a85450a497

KALSHI_DEMO_PRIMARY_DOMAIN_HISTORICAL_INCIDENT_RESOLUTION_DURABLE_RECONCILIATION_INGEST_STATE_UPDATE_SPEC_01.md
35105 bytes
cbe6313f1e2bc4ab007e3d30214aa2f95a80296eb9f352d36eb4936694d48e75

HANDOFF_KALSHI_DEMO_PRIMARY_DOMAIN_HISTORICAL_INCIDENT_RESOLUTION_DURABLE_RECONCILIATION_INGEST_STATE_UPDATE_SPEC_01.md
11085 bytes
67f2ac539f4a6cc4d9b8aa3c2401499c376bf44a0bebbafdcacf51c1b52038df
```

## Installation decision

The exact blob is approved for canonical archival placement at:

```text
project_archive/route_a_2026_08_26/ARB_ROUTE_A_ACCEPTED_PUBLIC_ARTIFACTS_2026_08_26.zip
```

The earlier connector-created 15009-byte object at that path is not the approved archive and must be replaced by exact Git blob `de4794e55eed4210e9541b95e93d262926b83c02`.

The temporary root-level upload path from the review commit is not required in the canonical tree.

## Safety/state consequence

None. This is public documentation/provenance retention only. The accepted incident remains unresolved, A3 remains consumed, A4 remains no-durable-ingest, writer proof remains HELD/ineligible, and no new execution capability is granted.
