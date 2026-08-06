# GUARDRAILS

## Authority level

This document is the highest standing operational authority in this repository. It can be changed only through the complete guardrail amendment process in Section 14. Until every step of that process is completed, the existing guardrail text remains controlling.

## 1. Permanent versus phase-specific rules

The rules in this document are permanent. Current phase status, active authorizations, and current-state facts belong in `PROJECT_STATE.md` and `AUTHORIZATION_LOG.md`, not here.

## 2. Authorization and approval

- Gustavo is the sole approval authority.
- Exact Gustavo authorization determines task-specific permission only within these guardrails.
- Ordinary task authorization cannot override a permanent guardrail.
- Anything missing, omitted, inherited, implied, or ambiguous is prohibited.

## 3. No-live-trading default

No live trading is permitted by default. Live or authenticated production trading activity requires separate, explicit Gustavo authorization.

## 4. Demo/production separation

Kalshi Demo and Kalshi production are structurally and operationally distinct. Demo access does not imply production access. Demo results are not production evidence and do not establish production safety, correctness, liquidity, or profitability.

## 5. Venue separation

Kalshi and Polymarket are not forced into identical order representations, settlement models, fee models, market identifiers, outcome semantics, tick or quantity units, lifecycle events, or authentication behavior. Venue-specific behavior belongs in the corresponding adapter. Shared economic concepts may use venue-independent types only where meaning is genuinely shared.

## 6. Credentials and secrets

Credentials and secrets are never committed to this repository. No `.env` files other than deliberately tracked `.example` placeholders, private keys, certificates containing private material, account identifiers, funding details, wallet secrets, copied environment values, private or signed URLs, venue tokens, or personal data.

## 7. Public repository boundary

This repository is public. Every contributor and agent must treat it as such.

## 8. Funding and production write prohibitions

Account funding is prohibited without explicit Gustavo authorization. Production writes are prohibited without separate, explicit Gustavo authorization. Access and technical capability do not imply authorization.

## 9. Economic correctness

No strategy is described as "arbitrage" until all required legs are filled or contractually locked and the payout relationship has been verified at rule level. Similarly named markets are not assumed economically equivalent without rule-level payout verification.

## 10. Monetary precision

Economic values (prices, cash, fees, P&L, balances, order values, settlement amounts, quantities where venue units require exact precision, inventory cost basis, incentive accounting) use decimal or fixed-point representations. Binary floating-point arithmetic is prohibited for these values.

## 11. Reconciliation and idempotency expectations

Future execution requires idempotency keys where supported, exact fill/order reconciliation, and explicit venue truth sources. Gross edge, fees, slippage, adverse selection, and forced-hedge cost are accounted separately. Incentives are not recognized until confirmed.

## 12. Risk and halt controls

Risk limits, emergency cancellation, and halt controls fail closed. No environment may silently fall back to another. Missing, unknown, or malformed environment selection halts. Contradictory endpoint/credential/environment combinations halt.

## 13. Scope control

No silent scope expansion. A bounded task authorization permits only its exact stated capabilities and paths.

## 14. Guardrail amendment process

A permanent guardrail changes only after all of the following are complete:

1. an explicit proposed amendment;
2. Marco review;
3. explicit Gustavo approval of the guardrail amendment;
4. path-specific authorization to modify this file;
5. an auditable decision record; and
6. completion of the authorized repository change.

Until all six steps are completed, the existing guardrail text remains controlling. An ordinary task authorization, including one issued by Gustavo for a non-guardrail task, is never interpreted as silently amending this file.

## 15. Conflict and fail-closed rules

Any conflict, ambiguity, or stale record uses the more restrictive interpretation and halts the affected work until corrected through an authorized change.
