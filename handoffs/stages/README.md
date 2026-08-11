# ARB Stage Navigation

This directory provides a stable stage-oriented navigation layer for ARB.

It does not replace:

- `project_context/PROJECT_STATE.md`;
- `project_context/ARTIFACT_INDEX.md`;
- accepted specifications;
- accepted handoffs;
- review records;
- task-specific execution evidence.

Those remain authoritative within their defined roles.

## Stage progression

Use the following stage numbering for new stage directories:

- `00_repository_bootstrap`
- `01_demo_environment`
- `02_connectivity_preflight`
- `03_orderbook_reconstruction`
- `04_one_order_lifecycle`
- `05_post_halt_reconciliation`
- `06_fill_event_ledger_reconciliation`
- `07_minimal_market_making`
- `08_profitability_accounting`
- `09_logical_arbitrage`
- `10_kalshi_production_read_only`
- `11_polymarket_production_read_only`
- `12_shadow_execution`
- `13_authenticated_production_canaries`

Create a stage directory only when there is useful canonical navigation material to place in it.
Do not create empty directories solely for appearance.

## Recommended stage README fields

A stage `README.md` should be concise and navigational:

- `stage_id`
- `status`
- `predecessor`
- `controlling_spec`
- `controlling_handoff`
- `implementation`
- `tests`
- `review_or_decision`
- `external_evidence_reference`
- `next_gate`

Where an artifact has an accepted exact identity, include its byte length, SHA-256, Git blob, or
commit identity as applicable.

## No duplicate source of truth

Do not copy an accepted specification into a stage directory if the canonical specification already
exists elsewhere in the repository.

Reference it by path and exact identity.

Raw execution evidence should remain external by default unless a separate task explicitly approves
repository storage. A stage may include a secret-safe evidence reference containing filename,
classification, byte length, SHA-256, task ID, and storage status.
