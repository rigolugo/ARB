# Route-A accepted public artifact archive — 2026-08-26

This directory is the canonical repository archive for the accepted public specifications and subordinate handoffs needed to reconstruct the current Route-A/A4 controlling chain without relying on chat memory or File Library availability.

It is archival/provenance material only. It grants no network, credential, venue, persistence, writer-release, Gate-D, production, or other execution capability.

## Archive identity

`ARB_ROUTE_A_ACCEPTED_PUBLIC_ARTIFACTS_2026_08_26.zip`
- raw bytes: `213438`
- SHA-256: `823ffab9cb048a010457c03efa2546a10c23413f561177cf93be49a1059fa222`
- ZIP CRC/member validation: `PASS`
- exact members: `10`

`ROUTE_A_ACCEPTED_PUBLIC_ARTIFACTS_MANIFEST_2026_08_26.json` records every member filename, raw byte length, and SHA-256.

## Included public artifacts

- `HANDOFF_KALSHI_DEMO_EMERGENCY_CANCELLATION_AND_RISK_LIMITS_SPEC_03.md` — 19785 bytes — SHA-256 `335048d61acd9367755629f90f584553ece7eed8553ffcf9c881a6feb4b944f3`
- `HANDOFF_KALSHI_DEMO_GATE_D_REAL_EXECUTION_SUBSTRATE_AND_WRITER_ELIGIBILITY_SPEC_01.md` — 15390 bytes — SHA-256 `57a37e444afcf0706adcc5f4f09bb280dc04c46a2fff8b4e678f6aead2dbaac8`
- `HANDOFF_KALSHI_DEMO_PERSISTENT_LEDGER_AND_RESTART_RECOVERY_SPEC_03.md` — 17942 bytes — SHA-256 `43dd06f5a7d976bff54574f60298c7568f74e9c24b8f257e32306b45c8289b93`
- `HANDOFF_KALSHI_DEMO_PRIMARY_DOMAIN_HISTORICAL_INCIDENT_RESOLUTION_DURABLE_RECONCILIATION_INGEST_STATE_UPDATE_SPEC_01.md` — 11085 bytes — SHA-256 `67f2ac539f4a6cc4d9b8aa3c2401499c376bf44a0bebbafdcacf51c1b52038df`
- `HANDOFF_KALSHI_DEMO_PRIMARY_DOMAIN_HISTORICAL_INCIDENT_RESOLUTION_READ_ONLY_SPEC_05.md` — 12304 bytes — SHA-256 `694d7a0bdb4af541b422a9ff617e7f2a2897987035a83c14b1e347a85450a497`
- `KALSHI_DEMO_EMERGENCY_CANCELLATION_AND_RISK_LIMITS_SPEC_03.md` — 183042 bytes — SHA-256 `bb8f078185eb766ed1589441712d9cc6fcd77f574a1a2100a1901cfb75e9c8cb`
- `KALSHI_DEMO_GATE_D_REAL_EXECUTION_SUBSTRATE_AND_WRITER_ELIGIBILITY_SPEC_01.md` — 68568 bytes — SHA-256 `512000eea8db5562768682ae1659c03c20a2b5093fba68ef37eae784039a8336`
- `KALSHI_DEMO_PERSISTENT_LEDGER_AND_RESTART_RECOVERY_SPEC_03.md` — 141566 bytes — SHA-256 `98592d719db2dcb59bb5ade6f18700b9acf4ae1049480f409b60f228f1518ead`
- `KALSHI_DEMO_PRIMARY_DOMAIN_HISTORICAL_INCIDENT_RESOLUTION_DURABLE_RECONCILIATION_INGEST_STATE_UPDATE_SPEC_01.md` — 35105 bytes — SHA-256 `cbe6313f1e2bc4ab007e3d30214aa2f95a80296eb9f352d36eb4936694d48e75`
- `KALSHI_DEMO_PRIMARY_DOMAIN_HISTORICAL_INCIDENT_RESOLUTION_READ_ONLY_SPEC_05.md` — 591027 bytes — SHA-256 `5e51550edf3a644b07a640631564be4e53d248e7fa73c86f29e8fa15316457d6`

## Deliberately excluded

- raw A3 execution ZIP/evidence payloads; their exact identities remain in the canonical current-state checkpoint;
- credentials, private keys, auth headers, account secrets, local database files, and other sensitive/local operational material;
- blocked/candidate predecessors that are not needed to reconstruct the current accepted Route-A/A4 contract.

## Recovery rule

After cloning the canonical repository, extract the ZIP and verify each reconstructed file against the manifest before using it as a controlling artifact. A filename alone is not sufficient; byte length and SHA-256 must match exactly.
