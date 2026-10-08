"""Offline pure fixture/oracle tests for the F03 Demo fee-semantics analyzer.

Controls: KALSHI_DEMO_R1_D07_F03_DEMO_FEE_SEMANTICS_TEST_SPEC_01_CORRECTION_02
(sections 7, 8, 12, 15, 17, 18).  The approved synthetic oracle
``F03_DEMO_FEE_SEMANTICS_OFFLINE_FIXTURES_CORRECTION_02.json`` is embedded
below byte-for-byte and its exact length / SHA-256 are asserted, so every case
here is driven by the reviewed oracle bytes rather than a paraphrase.  No
network, signer, credential, ledger or venue activity occurs.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import unittest
from decimal import Decimal as D

import arb.venues.kalshi.f03_fee_semantics_analyzer as A

FIXTURE_BYTES = 42329
FIXTURE_SHA256 = "ca3762bce161be05112937883ac593f53f7837dd1dd01973a413f29bd049d781"

# Cases exercised end-to-end at runner seams (tests/test_kalshi_f03_fee_semantics_runner.py).
RUNNER_FIXTURE_CASES = frozenset({
    "FX_CHECKPOINT_ZERO_SUCCESSES", "FX_CHECKPOINT_ONE_SUCCESS", "FX_CHECKPOINT_TWO_EQUAL",
    "FX_CHECKPOINT_THREE_LAST_EQUAL", "FX_CHECKPOINT_THREE_UNEQUAL", "FX_CHECKPOINT_FAILURE_PLUS_EQUAL",
    "FX_TIMESTAMP_REGRESSION", "FX_STALE_WATERMARK", "FX_NO_WALL_FRESHNESS_GATE", "FX_POST_BOUNDARY_FAILURE",
    "FX_PRE_BOUNDARY_FAILURE", "FX_FOURTH_CHECKPOINT_ATTEMPT", "FX_TENTH_BALANCE_GET", "FX_GET_201", "FX_CREATE3",
    "FX_CREATE_T3_NO_PHYSICAL", "FX_CREATE_AMBIGUOUS", "FX_CANCEL_AMBIGUOUS", "FX_CANCEL_RACE", "FX_PAGECAP",
    "FX_ACTIVE_DOMAIN_CANCEL", "FX_CREATE_ONLY_POST_ONLY", "FX_ORDERBOOK_SPECIAL", "FX_BALANCE_NOT_STAGE3",
    "FX_INSUFFICIENT_BALANCE", "FX_DEADLINE_TAIL", "FX_WORKING_BOUND", "FX_UNRELATED_SETTLEMENT",
})

_FIXTURE_JSON = r'''{
  "schema": "F03_DEMO_FEE_SEMANTICS_OFFLINE_FIXTURES_CORRECTION_02_V1",
  "synthetic_only": true,
  "venue_behavior_established": false,
  "cases": [
    {
      "id": "FX_DIRECT_MAXIMAL",
      "kind": "numeric",
      "synthetic": true,
      "requirements": [
        "F03-MATH-001",
        "F03-MA-005"
      ],
      "input": {
        "quantum": ".0001",
        "fills": [
          {
            "q": ".2",
            "p": ".55",
            "k": ".07"
          },
          {
            "q": ".2",
            "p": ".55",
            "k": ".07"
          },
          {
            "q": ".2",
            "p": ".55",
            "k": ".07"
          },
          {
            "q": ".2",
            "p": ".55",
            "k": ".07"
          }
        ],
        "initializer": "ZERO",
        "rebate_rule": "MAXIMAL",
        "terminal_rule": "NO_CREDIT"
      },
      "expected": {
        "hypothesis_rows": [
          {
            "quantity": "0.2",
            "price": "0.55",
            "k": "0.07",
            "M": "1",
            "h": "0.0001",
            "accumulator_before_hypothesis": "0",
            "model_fee": "0.003465",
            "trade_fee": "0.003465",
            "revenue": "-0.11",
            "aligned_change": "-0.1135",
            "rounding_fee": "0.000035",
            "before_rebate_hypothesis": "0.000035",
            "rebate_hypothesis": "0",
            "net_fee_hypothesis": "0.0035",
            "accumulator_after_hypothesis": "0.000035",
            "balance_change_hypothesis": "-0.1135"
          },
          {
            "quantity": "0.2",
            "price": "0.55",
            "k": "0.07",
            "M": "1",
            "h": "0.0001",
            "accumulator_before_hypothesis": "0.000035",
            "model_fee": "0.003465",
            "trade_fee": "0.003465",
            "revenue": "-0.11",
            "aligned_change": "-0.1135",
            "rounding_fee": "0.000035",
            "before_rebate_hypothesis": "0.00007",
            "rebate_hypothesis": "0",
            "net_fee_hypothesis": "0.0035",
            "accumulator_after_hypothesis": "0.00007",
            "balance_change_hypothesis": "-0.1135"
          },
          {
            "quantity": "0.2",
            "price": "0.55",
            "k": "0.07",
            "M": "1",
            "h": "0.0001",
            "accumulator_before_hypothesis": "0.00007",
            "model_fee": "0.003465",
            "trade_fee": "0.003465",
            "revenue": "-0.11",
            "aligned_change": "-0.1135",
            "rounding_fee": "0.000035",
            "before_rebate_hypothesis": "0.000105",
            "rebate_hypothesis": "0.0001",
            "net_fee_hypothesis": "0.0034",
            "accumulator_after_hypothesis": "0.000005",
            "balance_change_hypothesis": "-0.1134"
          },
          {
            "quantity": "0.2",
            "price": "0.55",
            "k": "0.07",
            "M": "1",
            "h": "0.0001",
            "accumulator_before_hypothesis": "0.000005",
            "model_fee": "0.003465",
            "trade_fee": "0.003465",
            "revenue": "-0.11",
            "aligned_change": "-0.1135",
            "rounding_fee": "0.000035",
            "before_rebate_hypothesis": "0.00004",
            "rebate_hypothesis": "0",
            "net_fee_hypothesis": "0.0035",
            "accumulator_after_hypothesis": "0.00004",
            "balance_change_hypothesis": "-0.1135"
          }
        ],
        "predicted_total": "0.0139",
        "per_fill_observation": false
      }
    },
    {
      "id": "FX_DIRECT_NONE",
      "kind": "numeric",
      "synthetic": true,
      "requirements": [
        "F03-MATH-001",
        "F03-MA-005"
      ],
      "input": {
        "quantum": ".0001",
        "fills": [
          {
            "q": ".2",
            "p": ".55",
            "k": ".07"
          },
          {
            "q": ".2",
            "p": ".55",
            "k": ".07"
          },
          {
            "q": ".2",
            "p": ".55",
            "k": ".07"
          },
          {
            "q": ".2",
            "p": ".55",
            "k": ".07"
          }
        ],
        "initializer": "ZERO",
        "rebate_rule": "NONE",
        "terminal_rule": "NO_CREDIT"
      },
      "expected": {
        "hypothesis_rows": [
          {
            "quantity": "0.2",
            "price": "0.55",
            "k": "0.07",
            "M": "1",
            "h": "0.0001",
            "accumulator_before_hypothesis": "0",
            "model_fee": "0.003465",
            "trade_fee": "0.003465",
            "revenue": "-0.11",
            "aligned_change": "-0.1135",
            "rounding_fee": "0.000035",
            "before_rebate_hypothesis": "0.000035",
            "rebate_hypothesis": "0",
            "net_fee_hypothesis": "0.0035",
            "accumulator_after_hypothesis": "0.000035",
            "balance_change_hypothesis": "-0.1135"
          },
          {
            "quantity": "0.2",
            "price": "0.55",
            "k": "0.07",
            "M": "1",
            "h": "0.0001",
            "accumulator_before_hypothesis": "0.000035",
            "model_fee": "0.003465",
            "trade_fee": "0.003465",
            "revenue": "-0.11",
            "aligned_change": "-0.1135",
            "rounding_fee": "0.000035",
            "before_rebate_hypothesis": "0.00007",
            "rebate_hypothesis": "0",
            "net_fee_hypothesis": "0.0035",
            "accumulator_after_hypothesis": "0.00007",
            "balance_change_hypothesis": "-0.1135"
          },
          {
            "quantity": "0.2",
            "price": "0.55",
            "k": "0.07",
            "M": "1",
            "h": "0.0001",
            "accumulator_before_hypothesis": "0.00007",
            "model_fee": "0.003465",
            "trade_fee": "0.003465",
            "revenue": "-0.11",
            "aligned_change": "-0.1135",
            "rounding_fee": "0.000035",
            "before_rebate_hypothesis": "0.000105",
            "rebate_hypothesis": "0",
            "net_fee_hypothesis": "0.0035",
            "accumulator_after_hypothesis": "0.000105",
            "balance_change_hypothesis": "-0.1135"
          },
          {
            "quantity": "0.2",
            "price": "0.55",
            "k": "0.07",
            "M": "1",
            "h": "0.0001",
            "accumulator_before_hypothesis": "0.000105",
            "model_fee": "0.003465",
            "trade_fee": "0.003465",
            "revenue": "-0.11",
            "aligned_change": "-0.1135",
            "rounding_fee": "0.000035",
            "before_rebate_hypothesis": "0.00014",
            "rebate_hypothesis": "0",
            "net_fee_hypothesis": "0.0035",
            "accumulator_after_hypothesis": "0.00014",
            "balance_change_hypothesis": "-0.1135"
          }
        ],
        "predicted_total": "0.014",
        "per_fill_observation": false
      }
    },
    {
      "id": "FX_NON_DIRECT_MAXIMAL",
      "kind": "numeric",
      "synthetic": true,
      "requirements": [
        "F03-MATH-001",
        "F03-MA-005"
      ],
      "input": {
        "quantum": ".01",
        "fills": [
          {
            "q": ".2",
            "p": ".55",
            "k": ".07"
          },
          {
            "q": ".2",
            "p": ".55",
            "k": ".07"
          },
          {
            "q": ".2",
            "p": ".55",
            "k": ".07"
          },
          {
            "q": ".2",
            "p": ".55",
            "k": ".07"
          }
        ],
        "initializer": "ZERO",
        "rebate_rule": "MAXIMAL",
        "terminal_rule": "NO_CREDIT"
      },
      "expected": {
        "hypothesis_rows": [
          {
            "quantity": "0.2",
            "price": "0.55",
            "k": "0.07",
            "M": "1",
            "h": "0.01",
            "accumulator_before_hypothesis": "0",
            "model_fee": "0.003465",
            "trade_fee": "0.003465",
            "revenue": "-0.11",
            "aligned_change": "-0.12",
            "rounding_fee": "0.006535",
            "before_rebate_hypothesis": "0.006535",
            "rebate_hypothesis": "0",
            "net_fee_hypothesis": "0.01",
            "accumulator_after_hypothesis": "0.006535",
            "balance_change_hypothesis": "-0.12"
          },
          {
            "quantity": "0.2",
            "price": "0.55",
            "k": "0.07",
            "M": "1",
            "h": "0.01",
            "accumulator_before_hypothesis": "0.006535",
            "model_fee": "0.003465",
            "trade_fee": "0.003465",
            "revenue": "-0.11",
            "aligned_change": "-0.12",
            "rounding_fee": "0.006535",
            "before_rebate_hypothesis": "0.01307",
            "rebate_hypothesis": "0.01",
            "net_fee_hypothesis": "0",
            "accumulator_after_hypothesis": "0.00307",
            "balance_change_hypothesis": "-0.11"
          },
          {
            "quantity": "0.2",
            "price": "0.55",
            "k": "0.07",
            "M": "1",
            "h": "0.01",
            "accumulator_before_hypothesis": "0.00307",
            "model_fee": "0.003465",
            "trade_fee": "0.003465",
            "revenue": "-0.11",
            "aligned_change": "-0.12",
            "rounding_fee": "0.006535",
            "before_rebate_hypothesis": "0.009605",
            "rebate_hypothesis": "0",
            "net_fee_hypothesis": "0.01",
            "accumulator_after_hypothesis": "0.009605",
            "balance_change_hypothesis": "-0.12"
          },
          {
            "quantity": "0.2",
            "price": "0.55",
            "k": "0.07",
            "M": "1",
            "h": "0.01",
            "accumulator_before_hypothesis": "0.009605",
            "model_fee": "0.003465",
            "trade_fee": "0.003465",
            "revenue": "-0.11",
            "aligned_change": "-0.12",
            "rounding_fee": "0.006535",
            "before_rebate_hypothesis": "0.01614",
            "rebate_hypothesis": "0.01",
            "net_fee_hypothesis": "0",
            "accumulator_after_hypothesis": "0.00614",
            "balance_change_hypothesis": "-0.11"
          }
        ],
        "predicted_total": "0.02",
        "per_fill_observation": false
      }
    },
    {
      "id": "FX_NON_DIRECT_NONE",
      "kind": "numeric",
      "synthetic": true,
      "requirements": [
        "F03-MATH-001",
        "F03-MA-005"
      ],
      "input": {
        "quantum": ".01",
        "fills": [
          {
            "q": ".2",
            "p": ".55",
            "k": ".07"
          },
          {
            "q": ".2",
            "p": ".55",
            "k": ".07"
          },
          {
            "q": ".2",
            "p": ".55",
            "k": ".07"
          },
          {
            "q": ".2",
            "p": ".55",
            "k": ".07"
          }
        ],
        "initializer": "ZERO",
        "rebate_rule": "NONE",
        "terminal_rule": "NO_CREDIT"
      },
      "expected": {
        "hypothesis_rows": [
          {
            "quantity": "0.2",
            "price": "0.55",
            "k": "0.07",
            "M": "1",
            "h": "0.01",
            "accumulator_before_hypothesis": "0",
            "model_fee": "0.003465",
            "trade_fee": "0.003465",
            "revenue": "-0.11",
            "aligned_change": "-0.12",
            "rounding_fee": "0.006535",
            "before_rebate_hypothesis": "0.006535",
            "rebate_hypothesis": "0",
            "net_fee_hypothesis": "0.01",
            "accumulator_after_hypothesis": "0.006535",
            "balance_change_hypothesis": "-0.12"
          },
          {
            "quantity": "0.2",
            "price": "0.55",
            "k": "0.07",
            "M": "1",
            "h": "0.01",
            "accumulator_before_hypothesis": "0.006535",
            "model_fee": "0.003465",
            "trade_fee": "0.003465",
            "revenue": "-0.11",
            "aligned_change": "-0.12",
            "rounding_fee": "0.006535",
            "before_rebate_hypothesis": "0.01307",
            "rebate_hypothesis": "0",
            "net_fee_hypothesis": "0.01",
            "accumulator_after_hypothesis": "0.01307",
            "balance_change_hypothesis": "-0.12"
          },
          {
            "quantity": "0.2",
            "price": "0.55",
            "k": "0.07",
            "M": "1",
            "h": "0.01",
            "accumulator_before_hypothesis": "0.01307",
            "model_fee": "0.003465",
            "trade_fee": "0.003465",
            "revenue": "-0.11",
            "aligned_change": "-0.12",
            "rounding_fee": "0.006535",
            "before_rebate_hypothesis": "0.019605",
            "rebate_hypothesis": "0",
            "net_fee_hypothesis": "0.01",
            "accumulator_after_hypothesis": "0.019605",
            "balance_change_hypothesis": "-0.12"
          },
          {
            "quantity": "0.2",
            "price": "0.55",
            "k": "0.07",
            "M": "1",
            "h": "0.01",
            "accumulator_before_hypothesis": "0.019605",
            "model_fee": "0.003465",
            "trade_fee": "0.003465",
            "revenue": "-0.11",
            "aligned_change": "-0.12",
            "rounding_fee": "0.006535",
            "before_rebate_hypothesis": "0.02614",
            "rebate_hypothesis": "0",
            "net_fee_hypothesis": "0.01",
            "accumulator_after_hypothesis": "0.02614",
            "balance_change_hypothesis": "-0.12"
          }
        ],
        "predicted_total": "0.04",
        "per_fill_observation": false
      }
    },
    {
      "id": "FX_CAP_ONLY",
      "kind": "numeric",
      "synthetic": true,
      "requirements": [
        "F03-MATH-001"
      ],
      "input": {
        "q": ".1",
        "p": ".55",
        "k": ".07",
        "h": ".01",
        "A": ".02"
      },
      "expected": {
        "row": {
          "quantity": "0.1",
          "price": "0.55",
          "k": "0.07",
          "M": "1",
          "h": "0.01",
          "accumulator_before_hypothesis": "0.02",
          "model_fee": "0.0017325",
          "trade_fee": "0.001733",
          "revenue": "-0.055",
          "aligned_change": "-0.06",
          "rounding_fee": "0.003267",
          "before_rebate_hypothesis": "0.023267",
          "rebate_hypothesis": "0",
          "net_fee_hypothesis": "0.005",
          "accumulator_after_hypothesis": "0.023267",
          "balance_change_hypothesis": "-0.06"
        },
        "overall_q01": "INCONCLUSIVE"
      }
    },
    {
      "id": "FX_DIRECT_TABLE",
      "kind": "numeric",
      "synthetic": true,
      "requirements": [
        "F03-MATH-001"
      ],
      "input": {
        "q": "1",
        "p": ".5",
        "k": ".07",
        "h": ".0001",
        "A": "0"
      },
      "expected": {
        "row": {
          "quantity": "1",
          "price": "0.5",
          "k": "0.07",
          "M": "1",
          "h": "0.0001",
          "accumulator_before_hypothesis": "0",
          "model_fee": "0.0175",
          "trade_fee": "0.0175",
          "revenue": "-0.5",
          "aligned_change": "-0.5175",
          "rounding_fee": "0",
          "before_rebate_hypothesis": "0",
          "rebate_hypothesis": "0",
          "net_fee_hypothesis": "0.0175",
          "accumulator_after_hypothesis": "0",
          "balance_change_hypothesis": "-0.5175"
        },
        "overall_q01": "INCONCLUSIVE_WITHOUT_ELIGIBLE_DISCRIMINATOR"
      }
    },
    {
      "id": "FX_NON_DIRECT_TABLE",
      "kind": "numeric",
      "synthetic": true,
      "requirements": [
        "F03-MATH-001"
      ],
      "input": {
        "q": "1",
        "p": ".5",
        "k": ".07",
        "h": ".01",
        "A": "0"
      },
      "expected": {
        "row": {
          "quantity": "1",
          "price": "0.5",
          "k": "0.07",
          "M": "1",
          "h": "0.01",
          "accumulator_before_hypothesis": "0",
          "model_fee": "0.0175",
          "trade_fee": "0.0175",
          "revenue": "-0.5",
          "aligned_change": "-0.52",
          "rounding_fee": "0.0025",
          "before_rebate_hypothesis": "0.0025",
          "rebate_hypothesis": "0",
          "net_fee_hypothesis": "0.02",
          "accumulator_after_hypothesis": "0.0025",
          "balance_change_hypothesis": "-0.52"
        },
        "overall_q01": "INCONCLUSIVE_WITHOUT_ELIGIBLE_DISCRIMINATOR"
      }
    },
    {
      "id": "FX_RESET_ZERO",
      "kind": "numeric",
      "synthetic": true,
      "requirements": [
        "F03-MATH-001"
      ],
      "input": {
        "q": ".2",
        "p": ".55",
        "k": ".07",
        "h": ".01",
        "A": "0"
      },
      "expected": {
        "row": {
          "quantity": "0.2",
          "price": "0.55",
          "k": "0.07",
          "M": "1",
          "h": "0.01",
          "accumulator_before_hypothesis": "0",
          "model_fee": "0.003465",
          "trade_fee": "0.003465",
          "revenue": "-0.11",
          "aligned_change": "-0.12",
          "rounding_fee": "0.006535",
          "before_rebate_hypothesis": "0.006535",
          "rebate_hypothesis": "0",
          "net_fee_hypothesis": "0.01",
          "accumulator_after_hypothesis": "0.006535",
          "balance_change_hypothesis": "-0.12"
        },
        "overall_q01": "INCONCLUSIVE_WITHOUT_ELIGIBLE_DISCRIMINATOR"
      }
    },
    {
      "id": "FX_RESET_CARRY",
      "kind": "numeric",
      "synthetic": true,
      "requirements": [
        "F03-MATH-001"
      ],
      "input": {
        "q": ".2",
        "p": ".55",
        "k": ".07",
        "h": ".01",
        "A": ".009605"
      },
      "expected": {
        "row": {
          "quantity": "0.2",
          "price": "0.55",
          "k": "0.07",
          "M": "1",
          "h": "0.01",
          "accumulator_before_hypothesis": "0.009605",
          "model_fee": "0.003465",
          "trade_fee": "0.003465",
          "revenue": "-0.11",
          "aligned_change": "-0.12",
          "rounding_fee": "0.006535",
          "before_rebate_hypothesis": "0.01614",
          "rebate_hypothesis": "0.01",
          "net_fee_hypothesis": "0",
          "accumulator_after_hypothesis": "0.00614",
          "balance_change_hypothesis": "-0.11"
        },
        "overall_q01": "INCONCLUSIVE_WITHOUT_ELIGIBLE_DISCRIMINATOR"
      }
    },
    {
      "id": "FX_SAME_ORDER_TAKER_MAKER",
      "kind": "numeric",
      "synthetic": true,
      "requirements": [
        "F03-MATH-001"
      ],
      "input": {
        "same_order": true,
        "q": ".2",
        "p": ".55"
      },
      "expected": {
        "rows": [
          {
            "quantity": "0.2",
            "price": "0.55",
            "k": "0.07",
            "M": "1",
            "h": "0.01",
            "accumulator_before_hypothesis": "0",
            "model_fee": "0.003465",
            "trade_fee": "0.003465",
            "revenue": "-0.11",
            "aligned_change": "-0.12",
            "rounding_fee": "0.006535",
            "before_rebate_hypothesis": "0.006535",
            "rebate_hypothesis": "0",
            "net_fee_hypothesis": "0.01",
            "accumulator_after_hypothesis": "0.006535",
            "balance_change_hypothesis": "-0.12"
          },
          {
            "quantity": "0.2",
            "price": "0.55",
            "k": "0.0175",
            "M": "1",
            "h": "0.01",
            "accumulator_before_hypothesis": "0.006535",
            "model_fee": "0.00086625",
            "trade_fee": "0.000867",
            "revenue": "-0.11",
            "aligned_change": "-0.12",
            "rounding_fee": "0.009133",
            "before_rebate_hypothesis": "0.015668",
            "rebate_hypothesis": "0.01",
            "net_fee_hypothesis": "0",
            "accumulator_after_hypothesis": "0.005668",
            "balance_change_hypothesis": "-0.11"
          }
        ],
        "carry_preserved": true,
        "observed_per_fill_rebate": false
      }
    },
    {
      "id": "FX_PUBLISHED_LITERAL",
      "kind": "numeric",
      "synthetic": true,
      "requirements": [
        "F03-MATH-001"
      ],
      "input": {
        "model_fee": ".00363825",
        "revenue": "-.055",
        "h": ".01",
        "A": "0"
      },
      "expected": {
        "trade_fee": ".003639",
        "aligned_change": "-.06",
        "rounding_fee": ".001361",
        "net_fee_hypothesis": ".005",
        "rebate_hypothesis": "0"
      }
    },
    {
      "id": "FX_AGGREGATE_COUNTEREXAMPLE",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-MA-002",
        "F03-MA-003"
      ],
      "input": {
        "actual_net_fees": [
          ".0035",
          ".0035",
          ".0034"
        ],
        "api_fee_costs": [
          ".0034",
          ".0035",
          ".0035"
        ],
        "eligible": true
      },
      "expected": {
        "actual_total": ".0104",
        "api_total": ".0104",
        "aggregate_fee_cost_consistency_state": "AGGREGATE_MATCH",
        "per_fill_fee_identification_state": "NOT_IDENTIFIABLE",
        "observed_rebates": [
          null,
          null,
          null
        ],
        "per_fill_equalities_allowed": false
      }
    },
    {
      "id": "FX_SINGLE_IDENTIFIED",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-MA-004",
        "F03-ISO-002"
      ],
      "input": {
        "B_pre": "10",
        "B_post": "9.4965",
        "principal": ".5",
        "fill_count": 1,
        "checkpoints": [
          "STABLE",
          "STABLE"
        ],
        "other_isolation_predicates_pass": true,
        "terminal_credit_excluded": true,
        "api_total": ".0035"
      },
      "expected": {
        "cash_interval_residual": "0.0035",
        "aggregate_fee_cost_consistency_state": "AGGREGATE_MATCH",
        "per_fill_fee_identification_state": "SINGLE_FILL_IDENTIFIED",
        "q01": "INCONCLUSIVE",
        "policy_conflict_from_field_mismatch": false
      }
    },
    {
      "id": "FX_SINGLE_FIELD_CONFLICT",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-MA-004",
        "F03-ISO-002"
      ],
      "input": {
        "B_pre": "10",
        "B_post": "9.4965",
        "principal": ".5",
        "fill_count": 1,
        "checkpoints": [
          "STABLE",
          "STABLE"
        ],
        "other_isolation_predicates_pass": true,
        "terminal_credit_excluded": true,
        "api_total": ".0034"
      },
      "expected": {
        "cash_interval_residual": "0.0035",
        "aggregate_fee_cost_consistency_state": "AGGREGATE_CONFLICT",
        "per_fill_fee_identification_state": "SINGLE_FILL_IDENTIFIED",
        "q01": "INCONCLUSIVE",
        "policy_conflict_from_field_mismatch": false
      }
    },
    {
      "id": "FX_MULTI_AGGREGATE_ONLY",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-MA-004",
        "F03-ISO-002"
      ],
      "input": {
        "B_pre": "10",
        "B_post": "9.4965",
        "principal": ".5",
        "fill_count": 2,
        "checkpoints": [
          "STABLE",
          "STABLE"
        ],
        "other_isolation_predicates_pass": true,
        "terminal_credit_excluded": true,
        "api_total": ".0035"
      },
      "expected": {
        "cash_interval_residual": "0.0035",
        "aggregate_fee_cost_consistency_state": "AGGREGATE_MATCH",
        "per_fill_fee_identification_state": "NOT_IDENTIFIABLE",
        "q01": "INCONCLUSIVE",
        "policy_conflict_from_field_mismatch": false
      }
    },
    {
      "id": "FX_SINGLE_TERMINAL_CREDIT_UNEXCLUDED",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-MA-004",
        "F03-ISO-002"
      ],
      "input": {
        "B_pre": "10",
        "B_post": "9.4965",
        "principal": ".5",
        "fill_count": 1,
        "checkpoints": [
          "STABLE",
          "STABLE"
        ],
        "other_isolation_predicates_pass": true,
        "terminal_credit_excluded": false,
        "api_total": ".0035"
      },
      "expected": {
        "cash_interval_residual": "0.0035",
        "aggregate_fee_cost_consistency_state": "INCONCLUSIVE",
        "per_fill_fee_identification_state": "NOT_IDENTIFIABLE",
        "q01": "INCONCLUSIVE",
        "policy_conflict_from_field_mismatch": false
      }
    },
    {
      "id": "FX_UNIQUE_AGGREGATE",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-Q01-001",
        "F03-MA-005"
      ],
      "input": {
        "eligible": true,
        "predictions": {
          "MAXIMAL": ".0139",
          "NO_REBATE": ".014"
        },
        "cash": ".0139",
        "h": ".0001",
        "positive_rebate_total": ".0001",
        "joint_assumptions": [
          "ZERO_INIT",
          "NO_TERMINAL_CREDIT",
          "NO_OTHER_ADJUSTMENTS"
        ],
        "family_complete_for_claim": true
      },
      "expected": {
        "unique_discriminator_state": "UNIQUE_MATCH",
        "q01": "OBSERVED_MATCH",
        "scope_mode": "AGGREGATE_HYPOTHESIS",
        "observed_per_fill_rebate": false,
        "universal_policy_proven": false
      }
    },
    {
      "id": "FX_EQUAL_AGGREGATE",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-MA-005"
      ],
      "input": {
        "eligible": true,
        "predictions": {
          "MAXIMAL_EARLY": ".0104",
          "DELAYED_SAME_TOTAL": ".0104"
        },
        "cash": ".0104",
        "h": ".0001"
      },
      "expected": {
        "unique_discriminator_state": "EQUAL_PREDICTIONS",
        "q01": "INCONCLUSIVE",
        "observed_per_fill_rebate": false
      }
    },
    {
      "id": "FX_CAP_ONLY_D03",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-Q01-001"
      ],
      "input": {
        "identified_net_fee": ".005",
        "hypothesis_ref": "FX_CAP_ONLY",
        "positive_discriminator": false
      },
      "expected": {
        "subobservation": "CAP_BOUND_MATCH",
        "overall_q01": "INCONCLUSIVE",
        "maximality_proven": false
      }
    },
    {
      "id": "FX_RESET_AGGREGATE_ZERO",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-Q02-001"
      ],
      "input": {
        "I2_eligible": true,
        "zero_predicted": ".01",
        "carry_predicted": "0",
        "cash": ".01",
        "h": ".01",
        "fill_count": 1,
        "joint_assumptions_explicit": true
      },
      "expected": {
        "q02": "OBSERVED_MATCH",
        "scope": "TESTED_ZERO_VS_CARRY_PAIR",
        "universal_initializer_proven": false,
        "amend_subcase": "NOT_APPLICABLE"
      }
    },
    {
      "id": "FX_RESET_AGGREGATE_CARRY",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-Q02-001"
      ],
      "input": {
        "I2_eligible": true,
        "zero_predicted": ".01",
        "carry_predicted": "0",
        "cash": "0",
        "h": ".01",
        "joint_assumptions_explicit": true
      },
      "expected": {
        "q02": "OBSERVED_CONFLICT",
        "scope": "JOINT_ZERO_START_HYPOTHESIS",
        "universal_policy_falsified": false
      }
    },
    {
      "id": "FX_TERMINAL_RESIDUAL_EQUIVALENT",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-Q03-001"
      ],
      "input": {
        "h": ".01",
        "modeled_residual": ".00614",
        "credit_rules": [
          "NONE",
          "FLOOR_TO_H"
        ],
        "explicit_terminal_accumulator_event": false
      },
      "expected": {
        "predicted_credits": [
          "0",
          "0"
        ],
        "q03": "INCONCLUSIVE",
        "discard_vs_hidden_preservation_identified": false
      }
    },
    {
      "id": "FX_SHARED_Q04",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-Q04-001"
      ],
      "input": {
        "q01_cash_evidence_ids": [
          "I1"
        ],
        "q04_cash_evidence_ids": [
          "I1"
        ],
        "aggregate_match": true
      },
      "expected": {
        "distinct_cash_interval_count": 1,
        "q04": "OBSERVED_MATCH",
        "q04_scope_mode": "AGGREGATE_CONSISTENCY",
        "independent_support_for_fee_hypothesis": false
      }
    },
    {
      "id": "FX_PDF_SCOPE",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-Q05-001"
      ],
      "input": {
        "single_fill_identified_net_fee": ".0175",
        "DIRECT": true,
        "p": ".5",
        "q": "1",
        "M": "1",
        "table": ".02",
        "authoritative_table_class_statement": false
      },
      "expected": {
        "table_as_exact_direct_fee_conflicts": true,
        "q05": "INCONCLUSIVE",
        "pdf_intended_account_class": null
      }
    },
    {
      "id": "FX_CHECKPOINT_ZERO_SUCCESSES",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-BAL-002"
      ],
      "input": {
        "balances": [],
        "failed_reads": 1,
        "same_domain_process": true,
        "updated_ts_nonregressing": true,
        "watermark_pass": true
      },
      "expected": {
        "state": "FAILED",
        "cash_eligible": false,
        "helper_called": false,
        "later_create_allowed": false
      }
    },
    {
      "id": "FX_CHECKPOINT_ONE_SUCCESS",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-BAL-002"
      ],
      "input": {
        "balances": [
          "1"
        ],
        "failed_reads": 0,
        "same_domain_process": true,
        "updated_ts_nonregressing": true,
        "watermark_pass": true
      },
      "expected": {
        "state": "NOT_STABLE",
        "cash_eligible": false,
        "helper_called": true,
        "later_create_allowed": false
      }
    },
    {
      "id": "FX_CHECKPOINT_TWO_EQUAL",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-BAL-002"
      ],
      "input": {
        "balances": [
          "1",
          "1.0000"
        ],
        "failed_reads": 0,
        "same_domain_process": true,
        "updated_ts_nonregressing": true,
        "watermark_pass": true
      },
      "expected": {
        "state": "STABLE",
        "cash_eligible": true,
        "helper_called": true,
        "later_create_allowed": true
      }
    },
    {
      "id": "FX_CHECKPOINT_THREE_LAST_EQUAL",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-BAL-002"
      ],
      "input": {
        "balances": [
          "1",
          "2",
          "2.0"
        ],
        "failed_reads": 0,
        "same_domain_process": true,
        "updated_ts_nonregressing": true,
        "watermark_pass": true
      },
      "expected": {
        "state": "STABLE",
        "cash_eligible": true,
        "helper_called": true,
        "later_create_allowed": true
      }
    },
    {
      "id": "FX_CHECKPOINT_THREE_UNEQUAL",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-BAL-002"
      ],
      "input": {
        "balances": [
          "1",
          "2",
          "3"
        ],
        "failed_reads": 0,
        "same_domain_process": true,
        "updated_ts_nonregressing": true,
        "watermark_pass": true
      },
      "expected": {
        "state": "NOT_STABLE",
        "cash_eligible": false,
        "helper_called": true,
        "later_create_allowed": false
      }
    },
    {
      "id": "FX_CHECKPOINT_FAILURE_PLUS_EQUAL",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-BAL-002"
      ],
      "input": {
        "balances": [
          "1",
          "1"
        ],
        "failed_reads": 1,
        "same_domain_process": true,
        "updated_ts_nonregressing": true,
        "watermark_pass": true
      },
      "expected": {
        "state": "FAILED",
        "cash_eligible": false,
        "helper_called": true,
        "later_create_allowed": false
      }
    },
    {
      "id": "FX_TIMESTAMP_REGRESSION",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-BAL-002"
      ],
      "input": {
        "updated_ts": [
          100,
          99
        ]
      },
      "expected": {
        "halt": "BALANCE_TIMESTAMP_REGRESSION",
        "cash_eligible": false
      }
    },
    {
      "id": "FX_STALE_WATERMARK",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-BAL-002"
      ],
      "input": {
        "updated_ts": [
          99,
          99
        ],
        "latest_fill_epoch_floor": 100
      },
      "expected": {
        "state": "NOT_STABLE",
        "cash_eligible": false
      }
    },
    {
      "id": "FX_NO_WALL_FRESHNESS_GATE",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-BAL-001"
      ],
      "input": {
        "updated_ts": [
          100,
          100
        ],
        "client_wall_epoch": 1000000,
        "no_new_fill": true,
        "values_equal": true
      },
      "expected": {
        "state": "STABLE",
        "client_wall_freshness_proven": false
      }
    },
    {
      "id": "FX_POST_BOUNDARY_FAILURE",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-BAL-003"
      ],
      "input": {
        "reader_error_count": 1,
        "attempts_before": 0,
        "GET_before": 10
      },
      "expected": {
        "attempts": 1,
        "GET_after": 11,
        "checkpoint": "FAILED",
        "refund": false,
        "retry": false
      }
    },
    {
      "id": "FX_PRE_BOUNDARY_FAILURE",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-BAL-003"
      ],
      "input": {
        "reader_error_count": 0,
        "attempts_before": 0,
        "GET_before": 10
      },
      "expected": {
        "attempts": 1,
        "GET_after": 10,
        "checkpoint": "FAILED",
        "retry": false
      }
    },
    {
      "id": "FX_FOURTH_CHECKPOINT_ATTEMPT",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-BAL-003"
      ],
      "input": {
        "attempts": 3,
        "next_requested": true
      },
      "expected": {
        "call_allowed": false,
        "halt": "BUDGET_EXCEEDED"
      }
    },
    {
      "id": "FX_TENTH_BALANCE_GET",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-BAL-003"
      ],
      "input": {
        "balance_GET": 9,
        "next_requested": true
      },
      "expected": {
        "call_allowed": false,
        "halt": "BUDGET_EXCEEDED"
      }
    },
    {
      "id": "FX_GET_201",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-BUDGET-004"
      ],
      "input": {
        "GET": 200,
        "next_requested": true
      },
      "expected": {
        "call_allowed": false,
        "halt": "BUDGET_EXCEEDED"
      }
    },
    {
      "id": "FX_CREATE3",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-WRITE-001"
      ],
      "input": {
        "create_T3": 2,
        "next_requested": true
      },
      "expected": {
        "send_allowed": false,
        "halt": "WRITE_LIMIT_CONSUMED"
      }
    },
    {
      "id": "FX_CREATE_T3_NO_PHYSICAL",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-COUNT-003"
      ],
      "input": {
        "T3_committed": true,
        "final_binding_failed": true
      },
      "expected": {
        "create_units_consumed": 1,
        "physical_sends": 0,
        "retry": false,
        "state": "HALTED_HELD"
      }
    },
    {
      "id": "FX_CREATE_AMBIGUOUS",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-WRITE-001"
      ],
      "input": {
        "T3_committed": true,
        "timeout": true
      },
      "expected": {
        "create_units_consumed": 1,
        "later_create_allowed": false,
        "resend": false,
        "state": "HALTED_HELD"
      }
    },
    {
      "id": "FX_CANCEL_AMBIGUOUS",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-WRITE-003"
      ],
      "input": {
        "T3_committed": true,
        "timeout": true
      },
      "expected": {
        "cancel_units_consumed": 1,
        "later_cancel_allowed": false,
        "resend": false,
        "state": "HALTED_HELD"
      }
    },
    {
      "id": "FX_CANCEL_RACE",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-WRITE-002"
      ],
      "input": {
        "pre_filled": ".4",
        "concurrent_fill": ".1",
        "final_fill": ".5"
      },
      "expected": {
        "authoritative_filled": ".5",
        "pre_remaining_not_assumed_refund": true,
        "fresh_conservation_required": true
      }
    },
    {
      "id": "FX_UNRELATED_SETTLEMENT",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-ISO-001"
      ],
      "input": {
        "preexisting_unsettled_position": true
      },
      "expected": {
        "cash_eligible": false,
        "new_create_allowed": false,
        "q01": "INCONCLUSIVE"
      }
    },
    {
      "id": "FX_WORKING_BOUND",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-ISO-001"
      ],
      "input": {
        "working_order_at_checkpoint": true
      },
      "expected": {
        "cash_eligible": false,
        "reservation_model_used": false
      }
    },
    {
      "id": "FX_DUPLICATE_CONFLICT",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-WRITE-004"
      ],
      "input": {
        "same_fill_id": true,
        "fee_values": [
          ".01",
          ".02"
        ]
      },
      "expected": {
        "halt": "FILL_DUPLICATE_CONFLICT",
        "cash_eligible": false
      }
    },
    {
      "id": "FX_PAGECAP",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-BUDGET-004"
      ],
      "input": {
        "page": 4,
        "cursor": "nonempty"
      },
      "expected": {
        "halt": "PAGINATION_LIMIT_EXHAUSTED",
        "cash_eligible": false
      }
    },
    {
      "id": "FX_ABSOLUTE_BALANCE_SHARED",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-EVID-001"
      ],
      "input": {
        "shared_keys": [
          "balance_dollars"
        ]
      },
      "expected": {
        "halt": "EVIDENCE_SANITIZATION_FAILED",
        "bundle_allowed": false
      }
    },
    {
      "id": "FX_ACTIVE_DOMAIN_CANCEL",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-D01-CANCEL-001"
      ],
      "input": {
        "active_subaccount": 2,
        "active_exchange_index": 3
      },
      "expected": {
        "T2_query": {
          "subaccount": 2,
          "exchange_index": 3
        },
        "T2_request_id_required": true,
        "protected_cancel_helper_called": false,
        "transport": "EXISTING_GATE_ADAPTER_ONLY"
      }
    },
    {
      "id": "FX_CREATE_ONLY_POST_ONLY",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-D01-CREATE-001"
      ],
      "input": {
        "builder_post_only": true
      },
      "expected": {
        "body_delta": {
          "post_only": false
        },
        "hash_after_delta": true,
        "permit": "issue_strategy1_gate_d_create_permit"
      }
    },
    {
      "id": "FX_ORDERBOOK_SPECIAL",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-D01-READ-001"
      ],
      "input": {
        "semantic": "GET_MARKET_ORDERBOOK"
      },
      "expected": {
        "generic_signed_reader_allowed": false,
        "consumer": "issue_orderbook/special_seam"
      }
    },
    {
      "id": "FX_BALANCE_NOT_STAGE3",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-BAL-001"
      ],
      "input": {
        "operation": "GET_BALANCE"
      },
      "expected": {
        "Stage3_member": false,
        "legacy_member": false,
        "consumer": "read_f03_balance_snapshot_v1"
      }
    },
    {
      "id": "FX_MISSING_FEE_FIELD",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-SRC-002"
      ],
      "input": {
        "fee_cost": null
      },
      "expected": {
        "cash_eligible": false,
        "economic_record": "INCOMPLETE",
        "policy_conclusion": "INCONCLUSIVE"
      }
    },
    {
      "id": "FX_INSUFFICIENT_BALANCE",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-BAL-004"
      ],
      "input": {
        "existing_balance_sufficient": false
      },
      "expected": {
        "new_create_allowed": false,
        "funding_allowed": false,
        "halt": "INSUFFICIENT_EXISTING_BALANCE"
      }
    },
    {
      "id": "FX_ACCOUNT_CLASS_UNKNOWN",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-PRE-007"
      ],
      "input": {
        "account_class": "UNRESOLVED"
      },
      "expected": {
        "new_create_allowed": false,
        "halt": "ACCOUNT_CLASS_UNRESOLVED"
      }
    },
    {
      "id": "FX_DEADLINE_TAIL",
      "kind": "semantic",
      "synthetic": true,
      "requirements": [
        "F03-COUNT-004"
      ],
      "input": {
        "active_closed": true,
        "proven_active_target": true
      },
      "expected": {
        "cancel_allowed": false,
        "read_only_tail_max_seconds": 120,
        "operator_recovery_outside_scope": true
      }
    }
  ]
}
'''


def _fixture() -> dict:
    return json.loads(_FIXTURE_JSON)


def _cases() -> dict:
    return {case["id"]: case for case in _fixture()["cases"]}


def _scope(account_class="DIRECT", quantum="0.0001"):
    return A.QuestionScopeV1(account_class, quantum, "KXTEST-F03", "KXTEST", "KXSERIES", "EPOCH-1", ("fee_rounding.md:x",))


def _interval(*, b_pre="10", b_post="9.4965", principals=(D(".5"),), api=(D(".0035"),), stable=True,
              predicates_pass=True, terminal_excluded=True, cid="I1"):
    preds = {name: ("PASS" if predicates_pass else "FAIL") for name in A.ISOLATION_PREDICATES}
    return A.analyze_cash_interval(A.CashIntervalInputV1(
        interval_id=cid, pre_checkpoint_state="STABLE" if stable else "NOT_STABLE", post_checkpoint_state="STABLE",
        cash_delta_pre_minus_post=A.interval_cash_delta_from_private(D(b_pre), D(b_post)),
        principals=tuple(principals), api_fee_costs=tuple(api), isolation_predicates=preds,
        terminal_credit_excluded=terminal_excluded, cash_evidence_id=cid,
    ))


class FixtureIdentityTests(unittest.TestCase):
    def test_embedded_oracle_is_the_exact_approved_bytes(self) -> None:
        raw = _FIXTURE_JSON.encode("utf-8")
        self.assertEqual(len(raw), FIXTURE_BYTES)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), FIXTURE_SHA256)
        fixture = _fixture()
        self.assertTrue(fixture["synthetic_only"])
        self.assertFalse(fixture["venue_behavior_established"])
        self.assertEqual(len(fixture["cases"]), 56)

    def test_every_case_is_owned_by_an_analyzer_or_runner_test(self) -> None:
        ids = set(_cases())
        handled_here = {name[len("test_"):].upper() for name in dir(AnalyzerFixtureCaseTests) if name.startswith("test_fx_")}
        self.assertEqual(ids, handled_here | RUNNER_FIXTURE_CASES)
        self.assertFalse(handled_here & RUNNER_FIXTURE_CASES)

    def test_numeric_row_count_23_plus_published_literal(self) -> None:
        rows = 0
        for case in _fixture()["cases"]:
            if case["kind"] != "numeric":
                continue
            exp = case["expected"]
            rows += len(exp.get("hypothesis_rows", ())) + len(exp.get("rows", ())) + (1 if "row" in exp else 0)
        self.assertEqual(rows, 23)


class AnalyzerFixtureCaseTests(unittest.TestCase):
    """One test per analyzer-owned oracle case id (test_fx_<id lower>)."""

    def _sequence(self, case_id: str) -> None:
        case = _cases()[case_id]
        i = case["input"]
        hyp = A.CandidateHypothesisV1("X", i["initializer"], i["rebate_rule"], i["terminal_rule"], ("ZERO_INIT",))
        fills = [A.FillModelInputV1(D(f["q"]), D(f["p"]), D(f["k"])) for f in i["fills"]]
        pred = A.predict_sequence(fills, h=D(i["quantum"]), hypothesis=hyp)
        self.assertEqual([r.as_canonical_mapping() for r in pred.rows], case["expected"]["hypothesis_rows"])
        self.assertEqual(A.canonical_decimal_text(pred.predicted_total), case["expected"]["predicted_total"])
        self.assertFalse(case["expected"]["per_fill_observation"])
        for row in pred.rows:
            self.assertEqual(row.evidence_class, A.EVIDENCE_CLASS_MODEL_HYPOTHESIS)

    def test_fx_direct_maximal(self) -> None:
        self._sequence("FX_DIRECT_MAXIMAL")

    def test_fx_direct_none(self) -> None:
        self._sequence("FX_DIRECT_NONE")

    def test_fx_non_direct_maximal(self) -> None:
        self._sequence("FX_NON_DIRECT_MAXIMAL")

    def test_fx_non_direct_none(self) -> None:
        self._sequence("FX_NON_DIRECT_NONE")

    def _single_row(self, case_id: str) -> A.HypothesisRowV1:
        case = _cases()[case_id]
        i = case["input"]
        arithmetic = A.published_fill_arithmetic(quantity=D(i["q"]), price=D(i["p"]), k=D(i["k"]), multiplier=D("1"), h=D(i["h"]))
        row = A.hypothesis_row(arithmetic, accumulator_before=D(i["A"]), rebate_rule=A.RebateRule.MAXIMAL)
        self.assertEqual(row.as_canonical_mapping(), case["expected"]["row"])
        return row

    def _q01_without_discriminator(self, expected: str) -> None:
        result = A.decide_q01(A.Q01InputV1(True, None, None), scope=_scope())
        self.assertEqual(result["status"], "NOT_OBSERVABLE")
        interval = _interval()
        result = A.decide_q01(A.Q01InputV1(True, interval, None), scope=_scope())
        self.assertEqual(result["status"], "INCONCLUSIVE")
        self.assertIn(expected, ("INCONCLUSIVE", "INCONCLUSIVE_WITHOUT_ELIGIBLE_DISCRIMINATOR"))

    def test_fx_cap_only(self) -> None:
        row = self._single_row("FX_CAP_ONLY")
        self.assertEqual(row.rebate_hypothesis, 0)
        self._q01_without_discriminator(_cases()["FX_CAP_ONLY"]["expected"]["overall_q01"])

    def test_fx_direct_table(self) -> None:
        self._single_row("FX_DIRECT_TABLE")
        self._q01_without_discriminator(_cases()["FX_DIRECT_TABLE"]["expected"]["overall_q01"])

    def test_fx_non_direct_table(self) -> None:
        self._single_row("FX_NON_DIRECT_TABLE")
        self._q01_without_discriminator(_cases()["FX_NON_DIRECT_TABLE"]["expected"]["overall_q01"])

    def test_fx_reset_zero(self) -> None:
        self._single_row("FX_RESET_ZERO")
        self._q01_without_discriminator(_cases()["FX_RESET_ZERO"]["expected"]["overall_q01"])

    def test_fx_reset_carry(self) -> None:
        row = self._single_row("FX_RESET_CARRY")
        self.assertGreater(row.rebate_hypothesis, 0)
        self._q01_without_discriminator(_cases()["FX_RESET_CARRY"]["expected"]["overall_q01"])

    def test_fx_same_order_taker_maker(self) -> None:
        case = _cases()["FX_SAME_ORDER_TAKER_MAKER"]
        hyp = A.CandidateHypothesisV1("X", "ZERO", "MAXIMAL", "NO_CREDIT", ("ZERO_INIT",))
        q, p = D(case["input"]["q"]), D(case["input"]["p"])
        pred = A.predict_sequence([A.FillModelInputV1(q, p, A.K_TAKER), A.FillModelInputV1(q, p, A.K_MAKER)],
                                  h=A.QUANTUM_NON_DIRECT, hypothesis=hyp)
        self.assertEqual([r.as_canonical_mapping() for r in pred.rows], case["expected"]["rows"])
        # Carry crosses maker/taker roles on the same order.
        self.assertEqual(pred.rows[1].accumulator_before_hypothesis, pred.rows[0].accumulator_after_hypothesis)
        self.assertTrue(case["expected"]["carry_preserved"])
        self.assertFalse(case["expected"]["observed_per_fill_rebate"])

    def test_fx_published_literal(self) -> None:
        case = _cases()["FX_PUBLISHED_LITERAL"]
        i, e = case["input"], case["expected"]
        arithmetic = A.published_fill_arithmetic(quantity=D("1"), price=D("0.5"), k=A.K_TAKER, multiplier=D("1"),
                                                 h=D(i["h"]), model_fee_override=D(i["model_fee"]), revenue_override=D(i["revenue"]))
        row = A.hypothesis_row(arithmetic, accumulator_before=D(i["A"]), rebate_rule=A.RebateRule.MAXIMAL)
        self.assertEqual(arithmetic.trade_fee, D(e["trade_fee"]))
        self.assertEqual(arithmetic.aligned_change, D(e["aligned_change"]))
        self.assertEqual(arithmetic.rounding_fee, D(e["rounding_fee"]))
        self.assertEqual(row.net_fee_hypothesis, D(e["net_fee_hypothesis"]))
        self.assertEqual(row.rebate_hypothesis, D(e["rebate_hypothesis"]))

    def test_fx_aggregate_counterexample(self) -> None:
        case = _cases()["FX_AGGREGATE_COUNTEREXAMPLE"]
        actual = [D(v) for v in case["input"]["actual_net_fees"]]
        api = [D(v) for v in case["input"]["api_fee_costs"]]
        principals = (D(".11"), D(".11"), D(".11"))
        cash_delta = A.exact_add(*principals, *actual)
        interval = _interval(b_pre=str(cash_delta), b_post="0", principals=principals, api=api)
        e = case["expected"]
        self.assertEqual(A.canonical_decimal_text(interval.cash_fee_total), A.canonical_decimal_text(D(e["actual_total"])))
        self.assertEqual(interval.api_fee_cost_total, D(e["api_total"]))
        self.assertEqual(interval.aggregate_fee_cost_consistency_state, e["aggregate_fee_cost_consistency_state"])
        self.assertEqual(interval.per_fill_fee_identification_state, e["per_fill_fee_identification_state"])
        self.assertEqual(list(A.observed_rebates_for_interval(interval, fill_count=3)), e["observed_rebates"])
        self.assertIsNone(interval.identified_net_fee)
        self.assertFalse(e["per_fill_equalities_allowed"])
        self.assertNotEqual(actual[0], api[0])  # aggregate equality does NOT imply per-fill equality

    def _cash_case(self, case_id: str, *, fills: int) -> None:
        case = _cases()[case_id]
        i, e = case["input"], case["expected"]
        principals = tuple(D(i["principal"]) / fills for _ in range(fills))
        api = (D(i["api_total"]),) + tuple(D("0") for _ in range(fills - 1))
        interval = _interval(b_pre=i["B_pre"], b_post=i["B_post"], principals=principals, api=api,
                             predicates_pass=i["other_isolation_predicates_pass"],
                             terminal_excluded=i["terminal_credit_excluded"])
        self.assertEqual(A.canonical_decimal_text(interval.cash_fee_total), e["cash_interval_residual"])
        self.assertEqual(interval.aggregate_fee_cost_consistency_state, e["aggregate_fee_cost_consistency_state"])
        self.assertEqual(interval.per_fill_fee_identification_state, e["per_fill_fee_identification_state"])
        q01 = A.decide_q01(A.Q01InputV1(True, interval, None, cap_bound_prediction=None), scope=_scope())
        self.assertEqual(q01["status"], e["q01"])
        # A cash/API field mismatch is never converted into a rebate-policy conflict.
        self.assertNotEqual(q01["status"], "OBSERVED_CONFLICT")
        self.assertFalse(e["policy_conflict_from_field_mismatch"])

    def test_fx_single_identified(self) -> None:
        self._cash_case("FX_SINGLE_IDENTIFIED", fills=1)

    def test_fx_single_field_conflict(self) -> None:
        self._cash_case("FX_SINGLE_FIELD_CONFLICT", fills=1)

    def test_fx_multi_aggregate_only(self) -> None:
        self._cash_case("FX_MULTI_AGGREGATE_ONLY", fills=2)

    def test_fx_single_terminal_credit_unexcluded(self) -> None:
        self._cash_case("FX_SINGLE_TERMINAL_CREDIT_UNEXCLUDED", fills=1)

    def test_fx_unique_aggregate(self) -> None:
        case = _cases()["FX_UNIQUE_AGGREGATE"]
        i, e = case["input"], case["expected"]
        preds = {k: D(v) for k, v in i["predictions"].items()}
        disc = A.discriminate(preds, observed=D(i["cash"]), h=D(i["h"]), eligible=i["eligible"])
        self.assertEqual(disc.state, e["unique_discriminator_state"])
        interval = _interval(b_pre="10.0139", b_post="9.6", principals=(D(".4"),), api=(D(".0139"),))
        result = A.decide_q01(A.Q01InputV1(True, interval, disc, ("MAXIMAL",), D(i["positive_rebate_total"]),
                                           tuple(i["joint_assumptions"])), scope=_scope())
        self.assertEqual(result["status"], e["q01"])
        self.assertEqual(result["scope_mode"], e["scope_mode"])
        self.assertEqual(result["joint_assumptions"], i["joint_assumptions"])
        self.assertIn("UNIVERSAL_VENUE_FEE_POLICY", result["does_not_prove"])
        self.assertIn("PER_FILL_REBATE_FROM_API_FEE_COST", result["does_not_prove"])
        self.assertTrue(result["equivalent_untested_alternatives"])
        self.assertFalse(e["observed_per_fill_rebate"])
        self.assertFalse(e["universal_policy_proven"])
        # The rival-matching branch is a scoped JOINT conflict, never a universal falsification.
        rival = A.discriminate(preds, observed=D(".014"), h=D(i["h"]), eligible=True)
        conflict = A.decide_q01(A.Q01InputV1(True, interval, rival, ("MAXIMAL",), D("0"), ("ZERO_INIT",)), scope=_scope())
        self.assertEqual(conflict["status"], "OBSERVED_CONFLICT")
        self.assertIn("UNIVERSAL_POLICY_FALSIFICATION", conflict["does_not_prove"])

    def test_fx_equal_aggregate(self) -> None:
        case = _cases()["FX_EQUAL_AGGREGATE"]
        i, e = case["input"], case["expected"]
        disc = A.discriminate({k: D(v) for k, v in i["predictions"].items()}, observed=D(i["cash"]), h=D(i["h"]), eligible=i["eligible"])
        self.assertEqual(disc.state, e["unique_discriminator_state"])
        result = A.decide_q01(A.Q01InputV1(True, _interval(), disc, ("MAXIMAL_EARLY",), D("1"), ("ZERO_INIT",)), scope=_scope())
        self.assertEqual(result["status"], e["q01"])
        # Rivals within < h are also nondiscriminating.
        near = A.discriminate({"A": D(".0104"), "B": D(".01045")}, observed=D(".0104"), h=D(".0001"), eligible=True)
        self.assertEqual(near.state, "EQUAL_PREDICTIONS")
        self.assertEqual(A.discriminate({"A": D("1"), "B": D("3")}, observed=D("2"), h=D(".01"), eligible=True).state, "NO_MATCH")
        self.assertEqual(A.discriminate({"A": D("1"), "B": D("3")}, observed=D("1"), h=D(".01"), eligible=False).state, "INELIGIBLE")
        # Correction01 F01: a singleton is never a rival comparison.
        single = A.discriminate({"A": D("1")}, observed=D("2"), h=D(".01"), eligible=True)
        self.assertEqual((single.state, single.ineligibility_reason), ("INELIGIBLE", "FAMILY_NOT_A_RIVAL_COMPARISON"))

    def test_fx_cap_only_d03(self) -> None:
        case = _cases()["FX_CAP_ONLY_D03"]
        i, e = case["input"], case["expected"]
        cap = _cases()[i["hypothesis_ref"]]["expected"]["row"]["net_fee_hypothesis"]
        interval = _interval(b_pre="10.06", b_post="10", principals=(D(".055"),), api=(D(".005"),))
        self.assertEqual(interval.identified_net_fee, D(i["identified_net_fee"]))
        result = A.decide_q01(A.Q01InputV1(True, interval, None, cap_bound_prediction=D(cap)), scope=_scope("NON_DIRECT", "0.01"))
        self.assertEqual(result["status"], e["overall_q01"])
        self.assertIn({"subobservation": e["subobservation"]}, result["subobservations"])
        self.assertFalse(e["maximality_proven"])
        self.assertIn("UNIVERSAL_MAXIMALITY", result["does_not_prove"])

    def test_fx_reset_aggregate_zero(self) -> None:
        case = _cases()["FX_RESET_AGGREGATE_ZERO"]
        i, e = case["input"], case["expected"]
        result = A.decide_q02(A.Q02InputV1(True, True, i["I2_eligible"], D(i["cash"]), D(i["zero_predicted"]),
                                           D(i["carry_predicted"]), D(i["h"]), ("MAXIMAL_PER_FILL_RULE",), "I2"), scope=_scope())
        self.assertEqual(result["status"], e["q02"])
        self.assertEqual(result["scoped_conclusion"], e["scope"])
        self.assertIn("UNIVERSAL_NEW_ORDER_INITIALIZER", result["does_not_prove"])
        self.assertIn({"subobservation": "AMEND_REPLACE_SUBCASE", "status": e["amend_subcase"]}, result["subobservations"])
        self.assertFalse(e["universal_initializer_proven"])

    def test_fx_reset_aggregate_carry(self) -> None:
        case = _cases()["FX_RESET_AGGREGATE_CARRY"]
        i, e = case["input"], case["expected"]
        result = A.decide_q02(A.Q02InputV1(True, True, i["I2_eligible"], D(i["cash"]), D(i["zero_predicted"]),
                                           D(i["carry_predicted"]), D(i["h"]), ("MAXIMAL_PER_FILL_RULE",), "I2"), scope=_scope())
        self.assertEqual(result["status"], e["q02"])
        self.assertEqual(result["scoped_conclusion"], e["scope"])
        self.assertIn("UNIVERSAL_POLICY_FALSIFICATION", result["does_not_prove"])
        self.assertFalse(e["universal_policy_falsified"])
        # Equal totals / missing I2 / missing cash observable.
        self.assertEqual(A.decide_q02(A.Q02InputV1(True, True, True, D("0"), D(".01"), D(".01"), D(".01"), ("X",)), scope=_scope())["status"], "INCONCLUSIVE")
        self.assertEqual(A.decide_q02(A.Q02InputV1(True, False, False, None, None, None, D(".01")), scope=_scope())["status"], "INCONCLUSIVE")
        self.assertEqual(A.decide_q02(A.Q02InputV1(True, True, True, None, D(".01"), D("0"), D(".01"), ("X",)), scope=_scope())["status"], "NOT_OBSERVABLE")

    def test_fx_terminal_residual_equivalent(self) -> None:
        case = _cases()["FX_TERMINAL_RESIDUAL_EQUIVALENT"]
        i, e = case["input"], case["expected"]
        credits = [A.canonical_decimal_text(A.terminal_credit(D(i["modeled_residual"]), h=D(i["h"]),
                                                              terminal_rule={"NONE": "NO_CREDIT", "FLOOR_TO_H": "FLOOR_TO_H_CREDIT"}[r]))
                   for r in i["credit_rules"]]
        self.assertEqual(credits, e["predicted_credits"])
        result = A.decide_q03(A.Q03InputV1(True, D(i["modeled_residual"]), D(i["h"]), i["explicit_terminal_accumulator_event"], True),
                              scope=_scope("NON_DIRECT", "0.01"))
        self.assertEqual(result["status"], e["q03"])
        self.assertIn("DISCARD_VS_HIDDEN_PRESERVATION", result["does_not_prove"])
        self.assertFalse(e["discard_vs_hidden_preservation_identified"])
        self.assertEqual(A.decide_q03(A.Q03InputV1(True, None, D(".01"), False, False), scope=_scope())["status"], "NOT_OBSERVABLE")

    def test_fx_shared_q04(self) -> None:
        case = _cases()["FX_SHARED_Q04"]
        i, e = case["input"], case["expected"]
        interval = _interval(cid=i["q04_cash_evidence_ids"][0])
        self.assertEqual(interval.aggregate_fee_cost_consistency_state, "AGGREGATE_MATCH")
        result = A.decide_q04(A.Q04InputV1(True, interval, tuple(i["q01_cash_evidence_ids"])), scope=_scope())
        self.assertEqual(result["status"], e["q04"])
        self.assertEqual(result["scope_mode"], e["q04_scope_mode"])
        self.assertIs(result["independent_support_for_fee_hypothesis"], e["independent_support_for_fee_hypothesis"])
        count = [s for s in result["subobservations"] if s.get("subobservation") == "DISTINCT_CASH_INTERVAL_COUNT"][0]["value"]
        self.assertEqual(count, e["distinct_cash_interval_count"])
        self.assertEqual(result["cash_evidence_independence"], "SHARED_AGGREGATE_IDENTITY")

    def test_fx_pdf_scope(self) -> None:
        case = _cases()["FX_PDF_SCOPE"]
        i, e = case["input"], case["expected"]
        result = A.decide_q05(A.Q05InputV1("DIRECT" if i["DIRECT"] else "NON_DIRECT", D(i["single_fill_identified_net_fee"]),
                                           D(i["q"]), D(i["p"]), D(i["M"]), i["authoritative_table_class_statement"], "I1"), scope=_scope())
        self.assertEqual(result["status"], e["q05"])
        cmp_ = [s for s in result["subobservations"] if s.get("subobservation") == "TABLE_CELL_COMPARISON"][0]
        self.assertIs(cmp_["table_as_exact_direct_fee_conflicts"], e["table_as_exact_direct_fee_conflicts"])
        self.assertIsNone(cmp_["pdf_intended_account_class"])
        self.assertEqual(cmp_["table_value"], A.canonical_decimal_text(D(i["table"])))
        self.assertIn("PDF_TABLE_INTENDED_ACCOUNT_CLASS", result["does_not_prove"])
        no_cell = A.decide_q05(A.Q05InputV1("DIRECT", None, None, None, None), scope=_scope())
        self.assertIn({"subobservation": "TABLE_PRICE_FILL", "status": "NOT_APPLICABLE"}, no_cell["subobservations"])
        self.assertEqual(A.decide_q05(A.Q05InputV1("UNRESOLVED", D(".02"), D("1"), D(".5"), D("1")), scope=_scope())["status"], "INCONCLUSIVE")

    def test_fx_duplicate_conflict(self) -> None:
        case = _cases()["FX_DUPLICATE_CONFLICT"]
        # The oracle's semantic values become canonical FixedPointDollars lexemes.
        base = _fill_row("f-1", fee=A.canonical_decimal_text(D(case["input"]["fee_values"][0])))
        other = _fill_row("f-1", fee=A.canonical_decimal_text(D(case["input"]["fee_values"][1])))
        a = A.parse_fill_fee_fields(base, **_FILL_SCOPE)
        b = A.parse_fill_fee_fields(other, **_FILL_SCOPE)
        self.assertEqual(len(A.merge_fill_observations({}, [a, A.parse_fill_fee_fields(base, **_FILL_SCOPE)])), 1)
        with self.assertRaises(A.F03AnalyzerError) as ctx:
            A.merge_fill_observations({}, [a, b])
        self.assertEqual(ctx.exception.code, case["expected"]["halt"])

    def test_fx_absolute_balance_shared(self) -> None:
        case = _cases()["FX_ABSOLUTE_BALANCE_SHARED"]
        for key in case["input"]["shared_keys"]:
            with self.assertRaises(A.F03AnalyzerError) as ctx:
                A.assert_shared_evidence_sanitized({"interval": {key: "123.4500"}})
            self.assertEqual(ctx.exception.code, case["expected"]["halt"])
        for marker in ("-----BEGIN FAKE PRIVATE KEY-----", "KALSHI-ACCESS-SIGNATURE: synthetic", "Bearer synthetic"):
            with self.assertRaises(A.F03AnalyzerError):
                A.assert_shared_evidence_sanitized({"note": marker})
        with self.assertRaises(A.F03AnalyzerError):
            A.assert_shared_evidence_sanitized({"fee": 0.0035})
        A.assert_shared_evidence_sanitized({"cash_fee_total": "0.0035", "n": 1, "ok": True, "x": None})

    def test_fx_missing_fee_field(self) -> None:
        case = _cases()["FX_MISSING_FEE_FIELD"]
        row = _fill_row("f-2")
        row["fee_cost"] = case["input"]["fee_cost"]
        with self.assertRaises(A.F03AnalyzerError):
            A.parse_fill_fee_fields(row, **_FILL_SCOPE)
        interval = A.analyze_cash_interval(A.CashIntervalInputV1(
            "I1", "STABLE", "STABLE", D(".5035"), (D(".5"),), (None,),
            {name: "PASS" for name in A.ISOLATION_PREDICATES}, True, "I1"))
        self.assertFalse(interval.eligibility)
        self.assertEqual(interval.economic_record, case["expected"]["economic_record"])
        q01 = A.decide_q01(A.Q01InputV1(True, interval, None), scope=_scope())
        self.assertEqual(q01["status"], case["expected"]["policy_conclusion"])

    def test_fx_account_class_unknown(self) -> None:
        case = _cases()["FX_ACCOUNT_CLASS_UNKNOWN"]
        with self.assertRaises(A.F03AnalyzerError) as ctx:
            A.quantum_for_account_class(case["input"]["account_class"])
        self.assertEqual(ctx.exception.code, case["expected"]["halt"])


_FILL_SCOPE = dict(expected_subaccount=1, expected_exchange_index=0, expected_ticker="KXTEST-F03", expected_order_id="ord-1")


def _fill_row(fill_id: str, *, fee: str = "0.0035", **over) -> dict:
    row = {
        "fill_id": fill_id, "trade_id": fill_id, "order_id": "ord-1", "ticker": "KXTEST-F03", "market_ticker": "KXTEST-F03",
        "exchange_index": 0, "subaccount_number": 1, "subaccount": 1, "outcome_side": "yes", "book_side": "bid",
        "side": "yes", "action": "buy", "count_fp": "0.20", "yes_price_dollars": "0.5500", "no_price_dollars": "0.4500",
        "is_taker": True, "created_time": "2026-08-17T13:00:01.000000Z", "ts": 1755435601, "fee_cost": fee,
    }
    row.update(over)
    return row


class ArithmeticDisciplineTests(unittest.TestCase):
    def test_exact_context_rejects_inexact_and_float(self) -> None:
        with self.assertRaises(Exception):
            A.exact_mul(D("1") / D("3"), D("1.0000000000000000000000000000000000000000000000000000000000001"))
        with self.assertRaises(A.F03AnalyzerError):
            A.published_fill_arithmetic(quantity=0.2, price=D(".5"), k=A.K_TAKER, multiplier=D("1"), h=A.QUANTUM_DIRECT)
        for bad in ("1e-3", "+0.1", " 0.1", "0.1234567", "NaN", "1,0", "01.5"):
            with self.assertRaises(A.F03AnalyzerError):
                A.parse_fixed_point_dollars(bad, name="x")

    def test_rounding_fee_bounds_hold_over_grid(self) -> None:
        for h in (A.QUANTUM_DIRECT, A.QUANTUM_NON_DIRECT):
            for cents in range(1, 81):
                p = D(cents) / D(100)
                for q in (D(".01"), D(".37"), D("1")):
                    a = A.published_fill_arithmetic(quantity=q, price=p, k=A.K_TAKER, multiplier=D("1"), h=h)
                    self.assertTrue(D("0") <= a.rounding_fee < h)
                    self.assertEqual(A.exact_add(a.aligned_change, a.trade_fee, a.rounding_fee), a.revenue)
                    for rule in A.RebateRule:
                        row = A.hypothesis_row(a, accumulator_before=D("0.009"), rebate_rule=rule)
                        self.assertGreaterEqual(row.net_fee_hypothesis, 0)
                        self.assertLessEqual(row.rebate_hypothesis, row.before_rebate_hypothesis)

    def test_conservative_outlay_bound_matches_spec(self) -> None:
        bound = A.conservative_outlay_bound(order_count=2, max_limit_price=D("0.8000"), taker_multiplier=D("1"))
        self.assertEqual(bound.max_positive_fills_per_order, 100)
        self.assertEqual(bound.max_trade_fee_sum, D("0.0176"))
        self.assertEqual(bound.rounding_fee_sum_strict_upper, D("1"))
        self.assertEqual(bound.per_order_strict_upper, D("1.8176"))
        self.assertEqual(bound.plan_strict_upper, A.SPEC_TWO_ORDER_OUTLAY_BOUND_USD)
        A.require_plan_within_outlay_bound(bound)
        too_big = A.conservative_outlay_bound(order_count=2, max_limit_price=D("0.9000"), taker_multiplier=D("1"))
        with self.assertRaises(A.F03AnalyzerError):
            A.require_plan_within_outlay_bound(too_big)

    def test_terminal_credit_never_invents_non_grid_refund(self) -> None:
        self.assertEqual(A.terminal_credit(D("0.0199"), h=D(".01"), terminal_rule="FLOOR_TO_H_CREDIT"), D("0.01"))
        self.assertEqual(A.terminal_credit(D("0.0099"), h=D(".01"), terminal_rule="FLOOR_TO_H_CREDIT"), D("0"))


class ChronologyAndEquivalenceTests(unittest.TestCase):
    def test_ties_enumerate_all_orderings_and_only_invariant_totals_are_eligible(self) -> None:
        f_t = A.FillModelInputV1(D(".2"), D(".55"), A.K_TAKER)
        f_m = A.FillModelInputV1(D(".2"), D(".55"), A.K_MAKER)
        tied = (A.TimedFillV1(f_t, "T"), A.TimedFillV1(f_m, "T"))
        self.assertEqual(len(A.admissible_orderings(tied)), 2)
        hyp = A.CandidateHypothesisV1("X", "ZERO", "MAXIMAL", "NO_CREDIT", ("ZERO_INIT",))
        totals = {A.predict_sequence(o, h=A.QUANTUM_NON_DIRECT, hypothesis=hyp).predicted_total for o in A.admissible_orderings(tied)}
        expected = None if len(totals) > 1 else next(iter(totals))
        self.assertEqual(A.invariant_prediction(tied, h=A.QUANTUM_NON_DIRECT, hypothesis=hyp), expected)
        sequenced = (A.TimedFillV1(f_t, "T", 2), A.TimedFillV1(f_m, "T", 1))
        self.assertEqual(len(A.admissible_orderings(sequenced)), 1)

    def test_enumeration_bound_is_inconclusive_not_fabricated(self) -> None:
        f = A.FillModelInputV1(D(".01"), D(".55"), A.K_TAKER)
        many = tuple(A.TimedFillV1(f, "T") for _ in range(8))
        hyp = A.CandidateHypothesisV1("X", "ZERO", "MAXIMAL", "NO_CREDIT", ("ZERO_INIT",))
        self.assertIsNone(A.invariant_prediction(many, h=A.QUANTUM_DIRECT, hypothesis=hyp))

    def test_order2_reset_separation_requires_every_path(self) -> None:
        levels = ((D("0.45"), D("0.40")), (D("0.48"), D("0.30")))
        paths = A.possible_fill_paths(levels)
        self.assertEqual(len(paths), 2)
        self.assertFalse(A.order2_reset_separable(paths, h=A.QUANTUM_DIRECT, carry_start=D("0")))
        self.assertIsInstance(A.order2_reset_separable(paths, h=A.QUANTUM_NON_DIRECT, carry_start=D("0.009")), bool)

    def test_order1_opportunity_predicate(self) -> None:
        ok = A.order1_opportunity(((D("0.52"), D("0.30")), (D("0.55"), D("0.40"))), limit_price=D("0.5000"))
        self.assertTrue(ok.eligible)
        self.assertEqual(ok.cumulative_quantity, D("0.70"))
        one_level = A.order1_opportunity(((D("0.55"), D("0.40")),), limit_price=D("0.5000"))
        self.assertFalse(one_level.eligible)
        too_much = A.order1_opportunity(((D("0.52"), D("0.60")), (D("0.55"), D("0.40"))), limit_price=D("0.5000"))
        self.assertFalse(too_much.eligible)
        self.assertFalse(A.order1_opportunity((), limit_price=D("0.8100")).eligible)
        self.assertFalse(A.order1_opportunity((), limit_price=D("0.50")).eligible)


_TIE = "2026-08-17T13:00:01.000000Z"


def _tied(quantities, price=".0101"):
    k = A.role_coefficient(is_taker=True)
    return [A.TimedFillV1(A.FillModelInputV1(D(q), D(price), k, D("1")), _TIE, None) for q in quantities]


class Correction01FamilyAndChronologyTests(unittest.TestCase):
    """BLOCK F01 (incomplete family) and F02 (chronology-bound escape)."""

    def test_f01_exact_counterexample_is_inconclusive_not_conflict(self) -> None:
        # DIRECT h=.0001, p=.0101, k=.07, M=1, tied .01/.99: maximal totals are
        # .0007/.0008 (order dependent), NO_REBATE .0008, observed .0008.
        h = D(".0001")
        chronology = A.assess_chronology(_tied((".01", ".99")))
        self.assertEqual((chronology.state, len(chronology.orderings)), (A.CHRONOLOGY_ENUMERATED, 2))
        family = A.default_candidate_family()
        maximal, none = family[0], family[1]
        self.assertEqual(sorted(A.predict_sequence(o, h=h, hypothesis=maximal).predicted_total for o in chronology.orderings),
                         [D(".0007"), D(".0008")])
        m = A.invariant_outcome(chronology, h=h, hypothesis=maximal)
        n = A.invariant_outcome(chronology, h=h, hypothesis=none)
        self.assertEqual((m.predicted_total, m.reason), (None, "ORDER_DEPENDENT_PREDICTION"))
        self.assertEqual((n.predicted_total, n.reason), (D(".0008"), "INVARIANT"))
        ids = (maximal.hypothesis_id, none.hypothesis_id)
        complete = A.discriminate({ids[0]: m.predicted_total, ids[1]: n.predicted_total}, observed=D(".0008"), h=h,
                                  eligible=True, required_ids=ids)
        self.assertEqual((complete.state, complete.matched_hypothesis_id, complete.ineligibility_reason),
                         ("INELIGIBLE", None, "FAMILY_MEMBER_PREDICTION_UNAVAILABLE"))
        # The pre-correction defect: the uncomputable maximal member dropped.
        dropped = A.discriminate({ids[1]: n.predicted_total}, observed=D(".0008"), h=h, eligible=True, required_ids=ids)
        self.assertEqual((dropped.state, dropped.ineligibility_reason), ("INELIGIBLE", "FAMILY_MEMBER_ABSENT"))
        singleton = A.discriminate({ids[1]: n.predicted_total}, observed=D(".0008"), h=h, eligible=True)
        self.assertEqual(singleton.state, "INELIGIBLE")
        q1 = A.decide_q01(A.Q01InputV1(True, _interval(), complete, (ids[0],), None, maximal.assumptions), scope=_scope())
        self.assertEqual(q1["status"], "INCONCLUSIVE")
        self.assertNotIn(q1["status"], ("OBSERVED_MATCH", "OBSERVED_CONFLICT"))

    def test_f01_order_dependent_positive_rebate_is_never_positive_evidence(self) -> None:
        disc = A.DiscriminationResultV1("UNIQUE_MATCH", "MAXIMAL_ZERO_NO_TERMINAL", ("MAXIMAL_ZERO_NO_TERMINAL",), ())
        q1 = A.decide_q01(A.Q01InputV1(True, _interval(), disc, ("MAXIMAL_ZERO_NO_TERMINAL",), None, ("ZERO_INIT",)), scope=_scope())
        self.assertEqual((q1["status"], q1["scoped_conclusion"]), ("INCONCLUSIVE", "POSITIVE_REBATE_COMPONENT_ORDER_DEPENDENT"))

    def test_f01_incomplete_or_none_member_cannot_produce_match_or_conflict(self) -> None:
        ids = ("A", "B")
        for preds in ({"A": D("1"), "B": None}, {"A": None, "B": D("1")}, {"A": D("1")}, {"A": D("1"), "B": D("2"), "C": D("3")}):
            with self.subTest(preds=preds):
                disc = A.discriminate(preds, observed=D("1"), h=D(".01"), eligible=True, required_ids=ids)
                self.assertEqual(disc.state, "INELIGIBLE")
                self.assertIsNone(disc.matched_hypothesis_id)
        with self.assertRaises(A.F03AnalyzerError):
            A.discriminate({"A": D("1"), "B": "1"}, observed=D("1"), h=D(".01"), eligible=True, required_ids=ids)

    def test_f02_chronology_bound_is_a_state_not_an_exception(self) -> None:
        h = D(".0001")
        hyp = A.default_candidate_family()[0]
        for n, state, count in ((6, A.CHRONOLOGY_ENUMERATED, 720), (7, A.CHRONOLOGY_ENUMERATED, 5040),
                                (8, A.CHRONOLOGY_BOUND_EXCEEDED, 0)):
            with self.subTest(n=n):
                chronology = A.assess_chronology(_tied(("0.10",) * n, price=".45"))
                self.assertEqual((chronology.state, len(chronology.orderings)), (state, count))
                self.assertEqual(chronology.usable, state != A.CHRONOLOGY_BOUND_EXCEEDED)
                outcome = A.invariant_outcome(chronology, h=h, hypothesis=hyp)
                if state == A.CHRONOLOGY_BOUND_EXCEEDED:
                    self.assertEqual((outcome.predicted_total, outcome.reason), (None, A.CHRONOLOGY_BOUND_EXCEEDED))
                    self.assertIsNone(A.invariant_prediction(_tied(("0.10",) * n, price=".45"), h=h, hypothesis=hyp))
        self.assertEqual(A.MAX_ORDERINGS_ENUMERATED, 5040)
        unique = A.assess_chronology([A.TimedFillV1(A.FillModelInputV1(D(".1"), D(".45"), D(".07")), i, None) for i in range(9)])
        self.assertEqual(unique.state, A.CHRONOLOGY_UNIQUE)
        with self.assertRaises(A.F03AnalyzerError):  # malformed input still fails closed
            A.invariant_outcome("not-an-assessment", h=h, hypothesis=hyp)


class SchemaValidationTests(unittest.TestCase):
    def test_strict_json_rejects_duplicates_floats_and_nonfinite(self) -> None:
        for text in ('{"a":1,"a":2}', '{"a":1.5}', '{"a":NaN}', '{"a":Infinity}'):
            with self.assertRaises(A.F03AnalyzerError):
                A.strict_json_loads(text)
        with self.assertRaises(A.F03AnalyzerError):
            A.strict_json_loads(b"\xff")
        self.assertEqual(A.strict_json_loads('{"a":"1.5"}'), {"a": "1.5"})

    def test_question_result_schema_is_closed(self) -> None:
        result = A.decide_q04(A.Q04InputV1(True, _interval(), ()), scope=_scope())
        A.validate_question_result_v1(dict(result))
        bad = dict(result)
        bad["status"] = "PROBABLY"
        with self.assertRaises(A.F03AnalyzerError):
            A.validate_question_result_v1(bad)
        extra = dict(result)
        extra["surprise"] = 1
        with self.assertRaises(A.F03AnalyzerError):
            A.validate_question_result_v1(extra)
        q04_bad = dict(result)
        q04_bad["independent_support_for_fee_hypothesis"] = True
        with self.assertRaises(A.F03AnalyzerError):
            A.validate_question_result_v1(q04_bad)
        missing = dict(result)
        del missing["proves"]
        with self.assertRaises(A.F03AnalyzerError):
            A.validate_question_result_v1(missing)

    def test_cash_interval_schema_rejects_absolute_balance_and_bad_lexemes(self) -> None:
        obj = {
            "schema": "CashFeeIntervalV1", "interval_id": "I1", "pre_checkpoint_id": "B0", "post_checkpoint_id": "B1",
            "ordered_order_ids": ["o"], "ordered_fill_ids": ["f"], "fill_count": 1, "principal_total": "0.5",
            "cash_fee_total": "0.0035", "api_fee_cost_total": "0.0035", "aggregate_fee_cost_consistency_state": "AGGREGATE_MATCH",
            "per_fill_fee_identification_state": "SINGLE_FILL_IDENTIFIED",
            "isolation_predicates": {name: {"state": "PASS", "evidence_refs": []} for name in A.ISOLATION_PREDICATES},
            "eligibility": True, "rejection_codes": [], "cash_evidence_id": "I1",
            "candidate_hypotheses": [{"id": "MAXIMAL_ZERO_NO_TERMINAL", "initializer": "ZERO", "rebate_rule": "MAXIMAL",
                                      "terminal_rule": "NO_CREDIT", "assumptions": ["ZERO_INIT"], "predicted_total": "0.0035",
                                      "positive_rebate_total": "0", "modeled_residual": "0"}],
            "unique_discriminator_state": "UNIQUE_MATCH", "matched_hypothesis_id": "MAXIMAL_ZERO_NO_TERMINAL",
        }
        A.validate_cash_fee_interval_v1(obj)
        for key, value in (("cash_fee_total", "3.5e-3"), ("cash_fee_total", "0.00350"), ("unique_discriminator_state", "MAYBE")):
            bad = json.loads(json.dumps(obj))
            bad[key] = value
            with self.assertRaises(A.F03AnalyzerError):
                A.validate_cash_fee_interval_v1(bad)
        leak = json.loads(json.dumps(obj))
        leak["balance_dollars"] = "1000.00"
        with self.assertRaises(A.F03AnalyzerError):
            A.validate_cash_fee_interval_v1(leak)

    def test_cash_interval_nested_objects_are_closed_and_references_resolve(self) -> None:
        """Correction01 F03: nested predicate / hypothesis objects are exact
        key sets, ints exclude bool, references resolve inside the record."""
        base = {
            "schema": "CashFeeIntervalV1", "interval_id": "I1", "pre_checkpoint_id": "B0", "post_checkpoint_id": "B1",
            "ordered_order_ids": ["o"], "ordered_fill_ids": ["f"], "fill_count": 1, "principal_total": "0.5",
            "cash_fee_total": "0.0035", "api_fee_cost_total": "0.0035", "aggregate_fee_cost_consistency_state": "AGGREGATE_MATCH",
            "per_fill_fee_identification_state": "SINGLE_FILL_IDENTIFIED",
            "isolation_predicates": {name: {"state": "PASS", "evidence_refs": []} for name in A.ISOLATION_PREDICATES},
            "eligibility": True, "rejection_codes": [], "cash_evidence_id": "I1",
            "candidate_hypotheses": [{"id": "MAXIMAL_ZERO_NO_TERMINAL", "initializer": "ZERO", "rebate_rule": "MAXIMAL",
                                      "terminal_rule": "NO_CREDIT", "assumptions": ["ZERO_INIT"], "predicted_total": "0.0035",
                                      "positive_rebate_total": "0", "modeled_residual": "0"}],
            "unique_discriminator_state": "UNIQUE_MATCH", "matched_hypothesis_id": "MAXIMAL_ZERO_NO_TERMINAL",
        }
        A.validate_cash_fee_interval_v1(json.loads(json.dumps(base)))

        def _mut(fn):
            obj = json.loads(json.dumps(base))
            fn(obj)
            return obj

        first = next(iter(A.ISOLATION_PREDICATES))
        mutations = {
            "predicate_missing": lambda o: o["isolation_predicates"].pop(first),
            "predicate_extra_key": lambda o: o["isolation_predicates"][first].update(note="x"),
            "predicate_state_unknown": lambda o: o["isolation_predicates"][first].update(state="MAYBE"),
            "eligible_with_unresolved_predicate": lambda o: o["isolation_predicates"][first].update(state="UNRESOLVED"),
            "hypothesis_extra_key": lambda o: o["candidate_hypotheses"][0].update(score="1"),
            "hypothesis_unknown_id": lambda o: o["candidate_hypotheses"][0].update(id="H"),
            "matched_unresolved": lambda o: o.update(matched_hypothesis_id="NO_REBATE_ZERO_NO_TERMINAL"),
            "matched_without_unique": lambda o: o.update(unique_discriminator_state="NO_MATCH"),
            "fill_count_bool": lambda o: o.update(fill_count=True),
            "fill_count_mismatch": lambda o: o.update(fill_count=2),
            "eligibility_int": lambda o: o.update(eligibility=1),
            "duplicate_fill_ids": lambda o: o.update(ordered_fill_ids=["f", "f"], fill_count=2),
            "unknown_checkpoint": lambda o: o.update(post_checkpoint_id="B9"),
        }
        for name, fn in mutations.items():
            with self.subTest(name), self.assertRaises(A.F03AnalyzerError):
                A.validate_cash_fee_interval_v1(_mut(fn))

    def test_fill_fee_parser_requires_source_fields_direction_and_scope(self) -> None:
        good = A.parse_fill_fee_fields(_fill_row("f-9"), **_FILL_SCOPE)
        self.assertEqual(good.api_fee_cost, D("0.0035"))
        self.assertTrue(good.is_taker)
        cases = [
            dict(trade_id="other"), dict(market_ticker="OTHER"), dict(outcome_side="no"), dict(book_side="ask"),
            dict(side="no"), dict(action="sell"), dict(is_taker="true"), dict(count_fp="0.2"), dict(fee_cost="1e-3"),
            dict(created_time="2026-08-17 13:00:01"), dict(subaccount_number=2), dict(exchange_index=1),
            dict(order_id="ord-2"), dict(yes_price_dollars="1.5000"),
        ]
        for over in cases:
            with self.subTest(over=over), self.assertRaises(A.F03AnalyzerError):
                A.parse_fill_fee_fields(_fill_row("f-9", **over), **_FILL_SCOPE)
        for field_name in ("trade_id", "market_ticker", "book_side", "no_price_dollars", "is_taker", "fee_cost", "created_time"):
            row = _fill_row("f-9")
            del row[field_name]
            with self.subTest(missing=field_name), self.assertRaises(A.F03AnalyzerError):
                A.parse_fill_fee_fields(row, **_FILL_SCOPE)


class PurityTests(unittest.TestCase):
    def test_module_is_pure(self) -> None:
        source = inspect.getsource(A)
        for forbidden in ("import socket", "import ssl", "http.client", "urllib", "os.environ", "open(", "requests",
                          "minimal_market_maker_experiment_runner", "execution_ledger", "time.time", "datetime.now"):
            self.assertNotIn(forbidden, source, forbidden)
        self.assertEqual(A.__all__, [])
        self.assertEqual(len(A.HaltCode), 33)
        self.assertEqual(set(A.QuestionStatus), {"OBSERVED_MATCH", "OBSERVED_CONFLICT", "INCONCLUSIVE", "NOT_OBSERVABLE", "NOT_APPLICABLE"})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
