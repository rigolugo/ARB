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

No other artifacts (generated, evidence, or otherwise) exist under this bootstrap implementation.
