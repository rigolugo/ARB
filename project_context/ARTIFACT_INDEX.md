# ARTIFACT_INDEX

Canonical index of artifacts. This document is a locator and classification record only; it is not an artifact store and indexing an entry does not authorize its creation, retention, or commit.

Fields: Artifact ID, Path or external location, Producing task, Producing agent, Creation date, Source commit or run ID, Environment classification, Generated versus canonical status, Sensitivity classification, Review state, Retention or ignore policy, Related specification, Related test run or evidence.

## Initial state

- No trading, connectivity, environment, or test artifacts exist in this repository.
- `.gitkeep` files (`src/.gitkeep`, `tests/.gitkeep`, `artifacts/.gitkeep`) are structural placeholders only and are not artifacts.
- Unindexed local artifacts have no accepted status.
- Indexing an entry in this file does not authorize its creation, retention, or commit.

## Entries

| Artifact ID | Path | Producing task | Producing agent | Creation date | Source commit/run | Environment | Generated/Canonical | Sensitivity | Review state | Retention/ignore policy | Related specification | Related evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ART-0001 | `specifications/SPEC_repository_bootstrap.md` | Candidate 10 bootstrap implementation | Neo | 2026-08-06 | this commit | n/a (documentation) | Canonical | Public | Marco `APPROVE`; Gustavo accepted | retained | this file | `reviews/REVIEW_repository_bootstrap_spec.md` |
| ART-0002 | `handoffs/HANDOFF_repository_bootstrap_spec.md` | Candidate 10 bootstrap implementation | Neo | 2026-08-06 | this commit | n/a (documentation) | Canonical | Public | reviewed | retained | ART-0001 | n/a |
| ART-0003 | `reviews/REVIEW_repository_bootstrap_spec.md` | Candidate 10 bootstrap implementation | Neo | 2026-08-06 | this commit | n/a (documentation) | Canonical | Public | Marco `APPROVE` | retained | ART-0001 | n/a |
| ART-0004 | `handoffs/HANDOFF_repository_bootstrap_implementation.md` | Candidate 10 bootstrap implementation | Neo | 2026-08-06 | this commit | n/a (documentation) | Canonical | Public | issued by Marco | retained | ART-0001 | n/a |

| ART-0005 | `specifications/SPEC_kalshi_demo_environment_separation_and_capability_envelope.md` | Kalshi Demo environment-separation Candidate 02 canonical installation | Neo | 2026-08-06 | `3d19bd9f3d3610f4af0304bfd3ecf833cfd8420d` | n/a (documentation) | Canonical | Public | Marco `APPROVE`; Gustavo accepted installed implementation at `3d19bd9f3d3610f4af0304bfd3ecf833cfd8420d` | retained | `SPEC_kalshi_demo_environment_separation_and_capability_envelope_CANDIDATE_02.md` (78876 bytes, sha256 4a676c4698411db6743d591595918e4ba7af221b7a7b67d86e807925d8b47bf2) | `reviews/REVIEW_kalshi_demo_environment_separation_and_capability_envelope_spec.md` |
| ART-0006 | `handoffs/HANDOFF_kalshi_demo_environment_separation_and_capability_envelope_spec.md` | Kalshi Demo environment-separation Candidate 02 canonical installation | Neo | 2026-08-06 | `3d19bd9f3d3610f4af0304bfd3ecf833cfd8420d` | n/a (documentation) | Canonical | Public | reviewed; Marco `APPROVE`; Gustavo accepted installed implementation at `3d19bd9f3d3610f4af0304bfd3ecf833cfd8420d` | retained | ART-0005 | `HANDOFF_kalshi_demo_environment_separation_and_capability_envelope_spec_CANDIDATE_02.md` (14114 bytes, sha256 a47d623c4a80048909e4e9df8e4c11904ff0e763ab4e242028bd0c81dcedee6d) |
| ART-0007 | `reviews/REVIEW_kalshi_demo_environment_separation_and_capability_envelope_spec.md` | Kalshi Demo environment-separation Candidate 02 canonical installation | Neo | 2026-08-06 | `3d19bd9f3d3610f4af0304bfd3ecf833cfd8420d` | n/a (documentation) | Canonical | Public | Marco `APPROVE`; Gustavo accepted installed implementation at `3d19bd9f3d3610f4af0304bfd3ecf833cfd8420d` | retained | ART-0005 | `REVIEW_kalshi_demo_environment_separation_and_capability_envelope_spec_CANDIDATE_02.md` (6213 bytes, sha256 6d665601c5eb0b35943e0a782a34141f45b13b9f3440c3052c85171d54fe3c9b) |
| ART-0008 | `handoffs/HANDOFF_kalshi_demo_environment_separation_and_capability_envelope_implementation.md` | Kalshi Demo environment-separation Candidate 02 canonical installation | Neo | 2026-08-06 | `3d19bd9f3d3610f4af0304bfd3ecf833cfd8420d` | n/a (documentation) | Canonical | Public | issued by Marco; Marco `APPROVE`; Gustavo accepted installed implementation at `3d19bd9f3d3610f4af0304bfd3ecf833cfd8420d` | retained | ART-0005 | `HANDOFF_kalshi_demo_environment_separation_and_capability_envelope_implementation_CANDIDATE_02.md` (18572 bytes, sha256 19ec68c938d2d72dfa769dfc4c40e638d1e5f97f2590abf4928a73b2ba720982) |

No other artifacts (generated, evidence, or otherwise) exist under this bootstrap implementation or this Kalshi Demo environment-separation Candidate 02 canonical installation. Package ZIPs, detached checksums, manifests, local commits, and temporary branches produced for browser transfer are not indexed here as canonical repository artifacts.
