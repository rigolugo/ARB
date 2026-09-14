# R1-D07 Stage 3A-3F CANARY_03 Proven Execution Harness Archive

Status: `ACCEPTED_CANONICAL_PROVENANCE`  
Harness class: `PROVEN_EXECUTION_HARNESS`  
Authorization state: `CONSUMED`  
Replay policy: `REPLAY_PROHIBITED`  
Reuse policy: `REFERENCE_TEMPLATE_ONLY`

This archive preserves the exact PowerShell launcher that produced the first accepted
`READ_PHASE_COMPLETE` R1-D07 Stage 3A-3F live Demo read-only result against the exact
market-grid correction candidate that was subsequently installed unchanged on canonical
`main`.

The launcher is preserved byte-for-byte for provenance. **It must not be executed again.**
Its embedded execution authorization identity is consumed. Any future run must use a new,
separately authorized task/authorization identity and freshly verified state.

## Exact proven launcher

`RUN_R1-D07_STAGE3A3F_PRECANONICAL_CANARY_03.ps1`

- bytes: `27623`
- SHA-256: `28eda8da7386233603f3afbb18fbc5005cfd71d384d9cc9e7f878143b9bed530`
- authorization: `R1-D07_STAGE3A3F_PRECANONICAL_CANARY_03_AUTHORIZATION_01`
- authorization disposition: `CONSUMED`

The `.sha256` sidecar in this directory is the exact sidecar distributed with the
launcher.

## Exact code identity tested

- commit: `a52949b37fe87c6f7595a7137d001e383b12ab55`
- tree: `0c9382bd73c8cbd9e07876408cb145d0fb2a2440`
- parent: `f5ed9bb3f55807e347f43285f57b057f3048168f`

The same exact commit was later installed on canonical `rigolugo/ARB` `main`.

## Accepted execution theorem

- selector: `SUCCEEDED`
- selected ticker at observation time: `KXTRUMPSAY-26SEP14-MOON`
- Stage 3 exit code: `0`
- Stage 3 status: `READ_PHASE_COMPLETE`
- elapsed: `18539 ms`
- pre-release requests consumed: `18`
- trusted dynamic read set:
  `ADRS2_8798c1f54ecd11695c39728a29931fc95fef6203ca2c588db714164c9e2c768c`
- Gate D: `NOT_ENTERED`
- Stage 3G+: `NOT_ENTERED`
- normal writer: `NOT_ACQUIRED`
- release-only: `NOT_ACQUIRED`
- write authorization: `NO_WRITE_AUTHORIZATION`

## Starting N1 trusted state

The launcher preflight required:

- trusted sequence: `14`
- trusted hash:
  `d3f88597cc22692c32a21fadaa2caed1057d77e786ca887597a3e1b80e4917a2`
- durable prestack fill:
  `07212270-bae1-9bda-8e24-cd2221a09d60`

That sequence/hash is the **starting** state verified before CANARY_03. The terminal
result does not independently report the post-run authority/ledger tail; future work must
re-read current N1 state rather than infer a post-run tail.

## Diagnostic risk configuration

Accepted candidate raw SHA-256:
`7266ca2a60d58b21547dca66e7016b37a4cbe9c5289e741f9b746b8296bc649c`

CANARY_03 diagnostic config SHA-256:
`ce29cc69997b36a8721b1c60c02c7e2b83176fbd0fcd2ceb4a4e63115f3e7074`

Only diagnostic delta:
`state_integrity.reconciliation_read_deadline_ms: 1000 -> 30000`

The successful diagnostic does **not** itself make `30000` permanent controlling policy.
The previously accepted `1000 ms` value was empirically falsified for the observed live
read topology; a separate bounded risk-config correction is required.

## Result capture provenance

`R1-D07_STAGE3A3F_PRECANONICAL_CANARY_03_TERMINAL_RESULT_CAPTURE.json` is a normalized,
lossless field capture of the terminal JSON pasted by the operator into the Marco chat.
No original on-disk result file was supplied, so this archive does not claim an original
raw-result-file byte identity.
