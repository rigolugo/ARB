# PROJECT STATE CHECKPOINT — 2026-09-04 — R1-B03 DYNAMIC SUBACCOUNT DOMAIN BINDING IMPLEMENTATION

Authority level: canonical current-state overlay, installed on canonical `main`.

This checkpoint records the canonical installation of the R1-B03/11 dynamic subaccount
execution-domain binding and risk-control implementation (Corrections 06 through 09), the
narrowest of which (Correction 09) closes the two remaining active-V2 fill-identity defects
found by Marco review. It supersedes older next-action text only where that text says the
subaccount-1 stack binding/risk-control implementation is still pending.

This checkpoint grants no production capability, no additional Kalshi/venue write, no
market-making execution, and no profitability or arbitrage claim by itself.

## 1. Status

```text
roadmap = ARB-R1
milestone = R1-B03/11
status = APPROVED_AND_CANONICALLY_INSTALLED
controlling_spec = Correction-02
controlling_spec_sha256 = 6e642fa488d171715a8b12794cbc0c7d896583aa03b968011b0c316a749efd74
```

## 2. Installed identity

```text
preinstall_main = 2ab58ef10e060f6909e35ee55a95464cd33ab75d
implementation_commit = 9fb33f153f06c0a42a05850d049f896705a7b315
implementation_tree = c82d920fac96cf1e50e966a13c628b7a7d0c69f8
implementation_parent = 2ab58ef10e060f6909e35ee55a95464cd33ab75d
```

```text
review_outer_bundle =
R1-B03_CORRECTION_09_MARCO_SUBMISSION_BUNDLE.zip
bytes = 531691
sha256 = de7c6b2ac0a8fdecea12a5d834f3ba0a5a379ef1699caf0208359ecf02443b65

marco_approval_handoff =
R1-B03_CORRECTION_09_MARCO_APPROVAL_HANDOFF.md
bytes = 4808
sha256 = c7f08d93e7a6071a3c11bc66c819b601cd4ef78e8697596cdf999a0bb97ec6dd

focused_tests = 1818 passed + 80 subtests
full_tests = 3408 passed + 568 subtests
```

## 3. Accepted technical facts

```text
selected execution domain = explicit subaccount + exchange index binding
historical primary SUBACCOUNT=0 hold = UNCHANGED (writer_proof_state = HELD)
dynamic current exchange-index domain = read authoritatively, never hard-coded
account-wide same-subaccount economics across current indices enter release/risk truth
exact retained N=1 settlement/position reconciliation = fail-closed
active V2 live acquisition uses the closed trusted read path
exact fill identity includes order_id; exact duplicate/conflict semantics are exactly-once
```

No production behavior, profitability, arbitrage, or additional Demo write is proven or
authorized by this checkpoint.

## 4. Next bounded roadmap action

```text
R1-B04/11 = OFFLINE_STATIC_AND_REGRESSION_VALIDATION
status = NOT_STARTED
authorization = REQUIRED_SEPARATELY
```

The September-10 Kalshi sharding continuity documentation remains a separate pending
documentation item and is not folded into this installation.

## 5. Canonicalization status of this file

```text
CANONICALIZATION_STATUS = INSTALLED
```

This file was installed on `main` by the documentation-only continuity commit whose parent
is exactly the implementation commit recorded in Section 2
(`9fb33f153f06c0a42a05850d049f896705a7b315`); that continuity commit's own exact SHA is
recorded in `R1-B03_CORRECTION_09_CANONICAL_INSTALLATION_RESULT.json` and the installation
completion report (a commit cannot record its own resulting SHA inside its own tree).

The canonicalization task itself performs repository documentation writes only. It performed
no Kalshi request, no credential use beyond the existing Git remote authentication mechanism,
no venue write, no persistent trading-state mutation, and no production activity.
