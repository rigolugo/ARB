# PROJECT STATE CHECKPOINT — 2026-09-05 — R1-B04 VALIDATION AND C05 REVIEW

Authority level: canonical current-state overlay, installed on canonical `main`.

This checkpoint canonically records the already completed R1-B04/11 offline static and
regression validation of the R1-B03 installed implementation, and the already completed
Marco R1-C05/11 formal review of that validation. It supersedes older next-action text only
where that text says R1-B04 remains not started or R1-C05 remains pending.

This checkpoint grants no production capability, no additional Kalshi/venue write, no
market-making execution, and no profitability or arbitrage claim by itself.

## 1. Status

```text
roadmap = ARB-R1

R1-B03/11 = APPROVED_AND_CANONICALLY_INSTALLED
R1-B04/11 = COMPLETE_AND_MARCO_APPROVED
R1-C05/11 = COMPLETE
R1-C06/11 = CANONICALIZATION_OF_B04_AND_C05_STATE
```

## 2. Exact canonical substrate validated by B04

```text
canonical_main_at_validation = 63b881b7c6c81d30608ba61dca0aaf840028e4ee
canonical_tree               = 8135ce38de40fabb0dfbb27959b604f0495043ac
canonical_parent             = 9fb33f153f06c0a42a05850d049f896705a7b315

installed_implementation_commit = 9fb33f153f06c0a42a05850d049f896705a7b315
installed_implementation_tree   = c82d920fac96cf1e50e966a13c628b7a7d0c69f8
installed_implementation_parent = 2ab58ef10e060f6909e35ee55a95464cd33ab75d
```

## 3. Exact R1-B04 accepted validation evidence

```text
R1-B04_OFFLINE_VALIDATION_EVIDENCE_BUNDLE.zip
bytes  = 23768
sha256 = 7a33fb39a7176324aabf4a95bceb0d6e4a0b0de79e4461d7dedd7dd4835d8678

focused = 1818 passed + 80 subtests; 0 failed/errors
full    = 3408 passed + 568 subtests; 0 failed/errors

T01_T158_mapping           = COMPLETE
unexplained_collection_delta = NONE
installed_12_path_identity = PASS
static_conformance         = PASS
final_git_status           = EMPTY
```

## 4. Exact Marco R1-C05 decision

```text
R1-C05_MARCO_REVIEW_HANDOFF.md
bytes  = 5015
sha256 = 5072f7013c90b464f74d354351266df0d9639b3d4352783c057a4fe79289a852

disposition        = APPROVE
material_findings  = NONE
correction_required = NONE
```

## 5. Preserved current technical facts

```text
historical primary SUBACCOUNT=0 writer proof remains HELD
historical unresolved exposure remains fail-closed / not rewritten to zero
dynamic current exchange-index domain is authoritative, not hard-coded
account-wide same-subaccount economics across current indices remain in release/risk truth
retained N=1 settlement/position reconciliation remains fail-closed
active-V2 trusted read/acquisition boundary remains the accepted implementation
exact active-V2 fill identity includes order_id
only exact duplicate fill identity deduplicates economically
contradictory same-fill-ID identity fails closed
tests are supporting evidence, not an independent capability grant
```

This checkpoint does NOT:
- authorize an R1-D07 Demo canary;
- authorize another Demo write/cancel/flatten;
- authorize credentials/venue activity;
- prove production behavior;
- prove profitability;
- prove arbitrage.

## 6. Next bounded roadmap action

```text
R1-D07/11 = NOT_STARTED
authorization = REQUIRED_SEPARATELY
```

The September-10 Kalshi sharding continuity documentation remains a separate pending
documentation item and is not folded into this checkpoint.

## 7. Canonicalization status of this file

```text
CANONICALIZATION_STATUS = INSTALLED
```

This file was installed on `main` by the R1-C06/11 documentation-only canonicalization
commit whose parent is exactly `63b881b7c6c81d30608ba61dca0aaf840028e4ee` (a commit cannot
record its own resulting SHA inside its own tree; the exact resulting C06 commit SHA is
recorded in the external `R1-C06_CANONICALIZATION_RESULT.json` / `R1-C06_CANONICALIZATION_HANDOFF.md`).

The canonicalization task itself performs repository documentation writes only. It performed
no Kalshi request, no credential use beyond the existing Git remote authentication mechanism,
no venue write, no persistent trading-state mutation, and no production activity.
