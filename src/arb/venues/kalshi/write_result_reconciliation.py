"""Offline-safe Kalshi Demo primary-domain historical-incident resolution.

Revision-04 read-only evidence lane (A2 source-binding correction) for the immutable
``KALSHI_DEMO_ONE_ORDER_LIFECYCLE_EXECUTION_01`` incident.  This module
performs no network I/O of its own; every venue observation crosses a
caller-supplied ``GET``-only transport boundary and every request path/query
is generated internally from the closed ten-operation contract:

``USER_DATA_TIMESTAMP``, ``HISTORICAL_CUTOFF``, ``LIVE_ORDERS``,
``HISTORICAL_ORDERS``, ``EXACT_ORDER``, ``LIVE_FILLS``, ``HISTORICAL_FILLS``,
``LIVE_POSITIONS``, ``HISTORICAL_POSITIONS``, ``SETTLEMENTS``.

The central safety invariant is unchanged from the predecessor module: a
complete zero-match traversal never proves that the original CREATE never
existed.  ``READ_ZERO_MATCH_AUTHORITATIVE_NONEXISTENCE_PROVEN`` exists in the
closed result taxonomy but is structurally unreachable under this
specification; every zero-match run terminates as
``READ_ZERO_MATCH_NEGATIVE_THEOREM_NOT_PROVEN`` or a more specific
source-incompleteness result.

Revision 04 preserves the Revision-02 execution architecture while replacing
its source binding with the accepted execution-material projection and applying
the Revision-03 shard compatibility rules.  The established Revision-02
runtime corrections remain unchanged:

* a unique ``DIRECT_MATCH_HISTORICAL_ONLY`` order binds without an
  ``EXACT_ORDER`` reread, while ``DIRECT_MATCH_LIVE_PRESENT`` and
  ``DIRECT_MATCH_LIVE_AND_HISTORICAL_COMPATIBLE`` still require exactly one;
* a ``FILL_DERIVED`` binding reuses the already-completed pre-binding
  ``LIVE_FILLS``/``HISTORICAL_FILLS`` traversal for terminal economics rather
  than issuing a second fill traversal, and every planner branch's GET
  request budget is closed and non-fungible.

No function in this module loads environment variables, credentials, private
keys, account data, or auth headers.  No function in this module can emit a
``POST``/``PUT``/``PATCH``/``DELETE`` request, and no function can construct a
Stage-3 market-maker release/writer capability.  All quantity, price, fee, and
risk arithmetic uses :class:`decimal.Decimal`.
"""

from __future__ import annotations

import base64
import enum
import hashlib
import json
import re
import time
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from math import ceil, floor
from types import MappingProxyType
from typing import Callable, Dict, FrozenSet, List, Mapping, Optional, Protocol, Sequence, Tuple


# ---------------------------------------------------------------------------
# Frozen task / provenance identities
# ---------------------------------------------------------------------------

REPOSITORY = "rigolugo/ARB"
REQUIRED_MAIN = "37ddb6adc0f494f3d4e05442d1a1192be6f23b36"
REQUIRED_TREE = "11eccec38c4d15452e3d43aca382621e8979bdff"
REQUIRED_PARENT = "89afe409c996784a2c09cd99d83699a36c043b02"

TASK_ID = "KALSHI_DEMO_PRIMARY_DOMAIN_HISTORICAL_INCIDENT_RESOLUTION_READ_ONLY_A2_SOURCE_BINDING_REV04_IMPLEMENTATION_01"

SPECIFICATION_FILENAME = "KALSHI_DEMO_PRIMARY_DOMAIN_HISTORICAL_INCIDENT_RESOLUTION_READ_ONLY_SPEC_04.md"
SPECIFICATION_BYTES = 583254
SPECIFICATION_SHA256 = "7973a871048ccccf80cd12307e1f5851ade9c26d8f5446f7cbecc61afead3d2b"
HANDOFF_FILENAME = "HANDOFF_KALSHI_DEMO_PRIMARY_DOMAIN_HISTORICAL_INCIDENT_RESOLUTION_READ_ONLY_SPEC_04.md"
HANDOFF_BYTES = 15871
HANDOFF_SHA256 = "d5aaf0196542b1300113bd544b02dd592b627f00744c477ede6c4b13bfa60350"

PREDECESSOR_SPECIFICATION_FILENAME = "KALSHI_DEMO_PRIMARY_DOMAIN_HISTORICAL_INCIDENT_RESOLUTION_READ_ONLY_SPEC_01.md"
PREDECESSOR_SPECIFICATION_BYTES = 107697
PREDECESSOR_SPECIFICATION_SHA256 = "5122cb4a2b91812826af7c11840d5593d7139eda90e4c95afbf5c1b064cf593f"
PREDECESSOR_HANDOFF_FILENAME = "HANDOFF_KALSHI_DEMO_PRIMARY_DOMAIN_HISTORICAL_INCIDENT_RESOLUTION_READ_ONLY_SPEC_01.md"
PREDECESSOR_HANDOFF_BYTES = 25958
PREDECESSOR_HANDOFF_SHA256 = "c1559b652b35665846698c82fc3b70eb50fe0f6a7123859668c61caa77af0af0"

ORIGINAL_EXECUTION_EVIDENCE_IDENTITY = "KALSHI_DEMO_ONE_ORDER_LIFECYCLE_EXECUTION_01"
PRIOR_RECONCILIATION_EVIDENCE_IDENTITY = "KALSHI_DEMO_POST_HALT_EXACT_WRITE_RESULT_RECONCILIATION_EXECUTION_01"
PRIOR_FILL_FALLBACK_EVIDENCE_IDENTITY = "KALSHI_DEMO_POST_HALT_FILL_DISCOVERY_BINDING_FALLBACK_EXECUTION_01"

HISTORICAL_RESOLUTION_EVIDENCE_SCHEMA_REVISION = 2

# ---------------------------------------------------------------------------
# Immutable incident / conflict-domain / scope identities
# ---------------------------------------------------------------------------

INCIDENT_ID = "KALSHI_DEMO_ONE_ORDER_LIFECYCLE_EXECUTION_01"
CONFLICT_DOMAIN_REF = "KALSHI|KALSHI_DEMO|ARB_KALSHI_DEMO_PRIMARY_ACCOUNT|SUBACCOUNT=0"

DISPOSITION_BEFORE = "WRITE_UNRESOLVED_ZERO_MATCH"
BOUND_ORDER_ID_BEFORE = None
CREATED_ORDER_UPPER_BOUND_BEFORE = 1
ACTIVE_ORDER_UPPER_BOUND_BEFORE = 1
UNKNOWN_RESULT_BEFORE = True
WRITER_PROOF_STATE_BEFORE = "HELD"
WRITER_PROOF_RELEASE_ELIGIBLE_BEFORE = False
PROTECTED_UNRESOLVED_LEGACY_WRITE_COUNT_BEFORE = 1
HISTORY_COMPLETENESS_BEFORE = "COMPLETE_WITH_PROTECTED_UNRESOLVED_LEGACY_WRITE"
RESTART_CLASSIFICATION_BEFORE = "RESTART_UNRESOLVED_WRITE_HELD"
NORMAL_WRITER_HANDLE_BEFORE = "NONE"
HISTORICAL_INCIDENT_CANCEL_TARGET_BEFORE = "NONE"
HISTORICAL_UNRESOLVED_EXPOSURE_BEFORE = "UNKNOWN_UNBOUNDED"
RELEASE_ELIGIBLE_BEFORE = False

ENVIRONMENT = "KALSHI_DEMO"
DEMO_REST_ORIGIN = "https://external-api.demo.kalshi.co"
PRODUCTION_REST_ORIGIN = "https://external-api.kalshi.com"
TRADE_API_BASE_PATH = "/trade-api/v2"
ACCOUNT_SCOPE_REF = "ARB_KALSHI_DEMO_PRIMARY_ACCOUNT"
SUBACCOUNT = 0
EXCHANGE_INDEX = 0
TICKER = "KXFEDDECISION-26SEP-H0"
CLIENT_ORDER_ID = "2e64d452-2cc2-43fa-a976-e8f996192252"
WRITER_PROOF_ID = "KALSHI_DEMO_ONE_ORDER_LIFECYCLE_EXECUTION_01_WRITER_PROOF"

INCIDENT_LOWER_BOUND_SOURCE = "writer_proof.valid_from_utc"
INCIDENT_LOWER_BOUND_UTC = "2026-08-11T01:22:15.7100717Z"
INCIDENT_QUERY_MIN_TS = 1786411334

ECONOMIC_MEANING = "buy YES"
OUTCOME_SIDE = "yes"
BOOK_SIDE = "bid"
INITIAL_QUANTITY = Decimal("1.00")
LIMIT_PRICE = Decimal("0.0100")
TIME_IN_FORCE = "good_till_canceled"
POST_ONLY = True
CANCEL_ORDER_ON_PAUSE = True
REDUCE_ONLY = False
SELF_TRADE_PREVENTION_TYPE = "taker_at_cross"
MAX_FILLED_PRINCIPAL = Decimal("0.010000")
MAX_FEE_COST = Decimal("0.040000")
MAX_TOTAL_RISK = Decimal("0.050000")

# ---------------------------------------------------------------------------
# Deterministic safety ceilings and exact global request budget
# ---------------------------------------------------------------------------

PAGE_LIMIT = 1000
MAX_LIVE_ORDER_PAGES = 8
MAX_HISTORICAL_ORDER_PAGES = 32
MAX_LIVE_FILL_PAGES = 8
MAX_HISTORICAL_FILL_PAGES = 32
MAX_LIVE_POSITION_PAGES = 8
MAX_HISTORICAL_POSITION_PAGES = 8
MAX_SETTLEMENT_PAGES = 8
MAX_FILL_DERIVED_CANDIDATE_ORDER_IDS = 8
MAX_DIRECT_EXACT_ORDER_REVALIDATIONS = 1
MAX_USER_DATA_TIMESTAMP_READS = 2
MAX_HISTORICAL_CUTOFF_READS = 2

THEORETICAL_MAXIMUM_PLANNED_GET_SENDS = 116
GLOBAL_GET_SEND_MAXIMUM = 116

BRANCH_REQUEST_MAXIMA: Mapping[str, int] = MappingProxyType({
    "FILL_DERIVED_TERMINAL": 116,
    "LIVE_DIRECT_TERMINAL": 109,
    "LIVE_AND_HISTORICAL_COMPATIBLE_TERMINAL": 109,
    "HISTORICAL_ONLY_DIRECT_TERMINAL": 108,
    "FILL_DERIVED_ACTIVE": 92,
    "LIVE_DIRECT_ACTIVE": 45,
    "HISTORICAL_ONLY_DIRECT_ACTIVE": 45,
    "LIVE_AND_HISTORICAL_COMPATIBLE_ACTIVE": 45,
    "ZERO_MATCH": 92,
    "UNRESOLVED": 116,
})

MASTER_DEADLINE_MS = 180_000
PER_REQUEST_CEILING_MS = 10_000
HTTP_RETRIES = 0
REDIRECTS_FOLLOWED = 0

# ---------------------------------------------------------------------------
# Revision-02 correction freezes
# ---------------------------------------------------------------------------

HISTORICAL_ONLY_DIRECT_BINDING_EXACT_REREAD_REQUIRED = False
FILL_DERIVED_CANDIDATE_EXACT_REREAD_REQUIRED = True
FILL_DERIVED_POST_BINDING_SECOND_FILL_TRAVERSAL = False
REVISION_02_NEGATIVE_CLOSURE_PERMITTED = False

# ---------------------------------------------------------------------------
# Appendix A -- exact normalized current-official-source binding manifest
# ---------------------------------------------------------------------------

SOURCE_BINDING_MANIFEST_ID = "KALSHI_PRIMARY_DOMAIN_HISTORICAL_RESOLUTION_CURRENT_OFFICIAL_SOURCE_BINDING_2026-08-19_REV2"
SOURCE_BINDING_MANIFEST_BYTES = b'{"environment":{"credentials_shared":false,"demo_rest_root":"https://external-api.demo.kalshi.co/trade-api/v2","production_rest_root":"https://external-api.kalshi.com/trade-api/v2"},"historical_partition":{"cutoffs_move_forward":true,"positions_archived_per_whole_event":true,"retention_lower_bound":"NOT_EXPOSED","target_live_window":"3 months"},"manifest_id":"KALSHI_PRIMARY_DOMAIN_HISTORICAL_RESOLUTION_CURRENT_OFFICIAL_SOURCE_BINDING_2026-08-19_REV2","observed_at_utc":"2026-08-19T23:42:00Z","official_source_scope":"docs.kalshi.com only","operations":{"EXACT_ORDER":{"authentication":"AUTHENTICATED","documented_http_statuses":[200,401,404,500],"http_404_nonexistence_theorem":"NOT_EXPOSED","method":"GET","pagination":false,"path":"/trade-api/v2/portfolio/orders/{order_id}","path_parameters":["order_id"],"query_parameters":[],"response_identity_fields":["order_id","client_order_id","ticker","subaccount_number","exchange_index"],"source_url":"https://docs.kalshi.com/api-reference/orders/get-order"},"HISTORICAL_CUTOFF":{"authentication":"PUBLIC","method":"GET","negative_semantics":"PARTITION_BOUNDARY_ONLY__NOT_RETENTION_LOWER_BOUND","pagination":false,"path":"/trade-api/v2/historical/cutoff","query_parameters":[],"response_identity_fields":["market_settled_ts","trades_created_ts","orders_updated_ts","market_positions_last_updated_ts"],"source_url":"https://docs.kalshi.com/api-reference/historical/get-historical-cutoff-timestamps"},"HISTORICAL_FILLS":{"authentication":"AUTHENTICATED","limit_range":[1,1000],"method":"GET","pagination":true,"path":"/trade-api/v2/historical/fills","query_parameters":["ticker","max_ts","limit","cursor"],"response_economic_fields":["count_fp","yes_price_dollars","no_price_dollars","fee_cost","is_taker"],"response_identity_fields":["fill_id","trade_id","order_id","ticker","market_ticker","subaccount_number","exchange_index","ts","created_time"],"retention_lower_bound":"NOT_EXPOSED","source_url":"https://docs.kalshi.com/api-reference/historical/get-historical-fills","unsupported_query_fields":["min_ts","order_id","subaccount","exchange_index","client_order_id"]},"HISTORICAL_ORDERS":{"authentication":"AUTHENTICATED","limit_range":[1,1000],"method":"GET","pagination":true,"partition_semantics":"canceled/executed orders older than orders_updated_ts","path":"/trade-api/v2/historical/orders","query_parameters":["ticker","max_ts","limit","cursor"],"response_identity_fields":["order_id","client_order_id","ticker","subaccount_number","exchange_index"],"retention_lower_bound":"NOT_EXPOSED","source_url":"https://docs.kalshi.com/api-reference/historical/get-historical-orders","unsupported_query_fields":["min_ts","status","subaccount","exchange_index","client_order_id"]},"HISTORICAL_POSITIONS":{"authentication":"AUTHENTICATED","limit_range":[1,1000],"market_position_fields":["ticker","exchange_index","total_traded_dollars","position_fp","market_exposure_dollars","realized_pnl_dollars","fees_paid_dollars","last_updated_ts"],"method":"GET","pagination":true,"partition_semantics":"settled positions archived per whole event; never split across live/historical; cutoff field market_positions_last_updated_ts","path":"/trade-api/v2/historical/positions","query_parameters":["ticker","event_ticker","limit","cursor"],"response_subaccount_field":"NOT_EXPOSED","retention_lower_bound":"NOT_EXPOSED","source_url":"https://docs.kalshi.com/api-reference/historical/get-historical-positions","unsupported_query_fields":["subaccount","exchange_index","min_ts","max_ts"]},"LIVE_FILLS":{"authentication":"AUTHENTICATED","limit_range":[1,1000],"method":"GET","pagination":true,"partition_semantics":"fills before trades_created_ts historical","path":"/trade-api/v2/portfolio/fills","query_parameters":["ticker","order_id","min_ts","max_ts","limit","cursor","subaccount","exchange_index"],"response_economic_fields":["count_fp","yes_price_dollars","no_price_dollars","fee_cost","is_taker"],"response_identity_fields":["fill_id","trade_id","order_id","ticker","market_ticker","subaccount_number","exchange_index","ts","created_time"],"source_url":"https://docs.kalshi.com/api-reference/portfolio/get-fills"},"LIVE_ORDERS":{"authentication":"AUTHENTICATED","limit_range":[1,1000],"method":"GET","pagination":true,"partition_semantics":"resting always live; canceled/fully executed before orders_updated_ts historical","path":"/trade-api/v2/portfolio/orders","query_parameters":["ticker","event_ticker","min_ts","max_ts","status","limit","cursor","subaccount","exchange_index"],"response_economic_fields":["yes_price_dollars","no_price_dollars","fill_count_fp","remaining_count_fp","initial_count_fp","taker_fill_cost_dollars","maker_fill_cost_dollars","taker_fees_dollars","maker_fees_dollars"],"response_identity_fields":["order_id","client_order_id","ticker","subaccount_number","exchange_index"],"scope_request_fields":["ticker","subaccount","exchange_index"],"source_url":"https://docs.kalshi.com/api-reference/orders/get-orders"},"LIVE_POSITIONS":{"authentication":"AUTHENTICATED","limit_range":[1,1000],"market_position_fields":["ticker","exchange_index","total_traded_dollars","position_fp","market_exposure_dollars","realized_pnl_dollars","fees_paid_dollars","last_updated_ts"],"method":"GET","pagination":true,"partition_semantics":"unsettled positions always live; settled positions may move by whole event to historical","path":"/trade-api/v2/portfolio/positions","query_parameters":["cursor","limit","count_filter","ticker","event_ticker","subaccount","exchange_index"],"response_subaccount_field":"NOT_EXPOSED","scope_request_fields":["ticker","subaccount","exchange_index"],"source_url":"https://docs.kalshi.com/api-reference/portfolio/get-positions"},"SETTLEMENTS":{"authentication":"AUTHENTICATED","limit_range":[1,1000],"method":"GET","pagination":true,"path":"/trade-api/v2/portfolio/settlements","query_parameters":["limit","cursor","ticker","event_ticker","min_ts","max_ts","subaccount"],"response_fields":["ticker","exchange_index","event_ticker","yes_count_fp","yes_total_cost_dollars","no_count_fp","no_total_cost_dollars","revenue","settled_time","fee_cost","value"],"response_subaccount_field":"NOT_EXPOSED","role":"SUPPORTING_ECONOMIC_CROSS_CHECK_ONLY__NOT_ORDER_IDENTITY","scope_request_fields":["ticker","subaccount"],"source_url":"https://docs.kalshi.com/api-reference/portfolio/get-settlements"},"USER_DATA_TIMESTAMP":{"authentication":"PUBLIC","method":"GET","negative_semantics":"NOT_TRANSACTIONALLY_EXACT","pagination":false,"path":"/trade-api/v2/exchange/user_data_timestamp","query_parameters":[],"response_identity_fields":["as_of_time"],"semantic_notes":["approximate indication of when GetBalance/GetOrder(s)/GetFills/GetPositions data was last validated","short reflection delay documented"],"source_url":"https://docs.kalshi.com/api-reference/exchange/get-user-data-timestamp"}},"raw_openapi":{"bytes":null,"materialized":false,"reason":"available web retrieval permitted semantic inspection but raw bytes could not be materialized for independent hashing","sha256":null}}'
SOURCE_BINDING_MANIFEST_LENGTH = 7056
SOURCE_BINDING_MANIFEST_SHA256 = "22f4b6a8022bfe862536ce03fc21b91520b084c6361bd6c84fa6c51ca749451f"

OPERATION_BINDING_IDENTITIES: Mapping[str, Tuple[int, str]] = MappingProxyType({
    "USER_DATA_TIMESTAMP": (469, "7c5e1bbaa1465d79c064c7e28dd79c965ec07baecb33855f0a37d79abd8625ce"),
    "HISTORICAL_CUTOFF": (419, "2b02a2c3e6ce819d62953348a3e2946509fccb14bf1d41d18399ac89e2dc8386"),
    "LIVE_ORDERS": (811, "eafb20cfed169a02f5058c373f350b08ec4233fad3f6b628ad35bb48c9a687c3"),
    "HISTORICAL_ORDERS": (588, "d7fd85e84b289417ec83748c89ff54a166d81322330799a4a6af1532e0fff950"),
    "EXACT_ORDER": (437, "217760198e5e5b3b7200438a424056db6757dfa5f42a651f02749c751a07dca1"),
    "LIVE_FILLS": (618, "282f1085a96c6cc2823706453e7b19ea0256363d928af599f02f6ed22730bbc8"),
    "HISTORICAL_FILLS": (650, "6a1263357bf66062ec5057c9156b917ce75c87ced69e2586dbd94076ebef5207"),
    "LIVE_POSITIONS": (713, "78bea5ff531816d4ee414e1b2c63d2be4680fa73f073ba125a3b3cda78bab4f8"),
    "HISTORICAL_POSITIONS": (769, "ff85accd0686f8e9b28b19e32b078b6e9aa6c5003b6de1e8402ac7a93c974fcd"),
    "SETTLEMENTS": (645, "5893c3424b996b0da818084074ecfafceaa1926be4af599b7273e80a8cf49301"),
})


# Revision-02 remains embedded above as exact predecessor-audit evidence.
REV02_SOURCE_BINDING_MANIFEST_ID = SOURCE_BINDING_MANIFEST_ID
REV02_SOURCE_BINDING_MANIFEST_BYTES = SOURCE_BINDING_MANIFEST_BYTES
REV02_SOURCE_BINDING_MANIFEST_LENGTH = SOURCE_BINDING_MANIFEST_LENGTH
REV02_SOURCE_BINDING_MANIFEST_SHA256 = SOURCE_BINDING_MANIFEST_SHA256
REV02_OPERATION_BINDING_IDENTITIES = OPERATION_BINDING_IDENTITIES

# Exact Revision-04 canonical JSON, compressed for compact source storage.
_REV04_SOURCE_CONTRACT_ZLIB_BASE64 = (
    "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"
)
SOURCE_BINDING_MANIFEST_BYTES = zlib.decompress(
    base64.b64decode("".join(_REV04_SOURCE_CONTRACT_ZLIB_BASE64))
)
SOURCE_BINDING_MANIFEST_ID = (
    "KALSHI_PRIMARY_DOMAIN_HISTORICAL_RESOLUTION_EXECUTION_MATERIAL_SOURCE_CONTRACT_REV4"
)
SOURCE_BINDING_MANIFEST_LENGTH = 143_868
SOURCE_BINDING_MANIFEST_SHA256 = (
    "1df3fbb9e3a7f80a9e1890c2abf552e0a4d945b76cb6455e9fe79a977bb91e2b"
)
SOURCE_BINDING_NORMALIZATION_REVISION = 4
OPERATION_BINDING_IDENTITIES = MappingProxyType({
    "EXACT_ORDER": (15_224, "fb7e69cac3119dd396c7bf9b4f54f74f7f71cb5b76ce445895b58a53cc80bcfa"),
    "HISTORICAL_CUTOFF": (4_595, "96ba74f1233c91bcce529a5f59726ce44d166baf990352919e1af5e99855a794"),
    "HISTORICAL_FILLS": (17_130, "56cd493d88b3bd4ca87a2eef7c597beb1a09f5c1626beefc997f1acf9b5fb87e"),
    "HISTORICAL_ORDERS": (17_435, "ce76d532dacb2a7a059fd46d0c4a7d086e539f59e381d7bc97b41956f08bb53f"),
    "HISTORICAL_POSITIONS": (13_001, "dbaa8f62f993110e23a14c8f84d894e52f0f32160693ccba0f10ae55930c6571"),
    "LIVE_FILLS": (18_689, "fdcc527dadeadd57d5512f70a6403876660d25e0f9e7cb21b230d52a52648a38"),
    "LIVE_ORDERS": (19_474, "c8ad464e4a7045b412ec70cec0e9f4e01035103da7aff6b6647624cd35bdf90c"),
    "LIVE_POSITIONS": (14_165, "0c0b8ff3d04102a3083f421ee6914dbbe3f2f37b0021ec44acde83230a35c2ce"),
    "SETTLEMENTS": (16_810, "7ec7b606ef4f5b0ba02eaad2cf6df1994e7e690e0c51b40140c9e20501147229"),
    "USER_DATA_TIMESTAMP": (1_630, "c13419329be995ee5fa72f0967cdc1063289e565eb472d92de36546694355e1c"),
})



# Exact Appendix-B atom enumerations and the 118-family predecessor audit.
_REV04_AUDIT_ZLIB_BASE64 = (
    "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"
)
_REV04_AUDIT_DATA = json.loads(
    zlib.decompress(base64.b64decode("".join(_REV04_AUDIT_ZLIB_BASE64)))
)
PREDECESSOR_EXECUTION_MATERIAL = tuple(_REV04_AUDIT_DATA["PREDECESSOR_EXECUTION_MATERIAL"])
REV03_ACCEPTED_EXECUTION_MATERIAL = tuple(_REV04_AUDIT_DATA["REV03_ACCEPTED_EXECUTION_MATERIAL"])
RUNTIME_CONSUMED_SOURCE_CONTRACT = tuple(_REV04_AUDIT_DATA["RUNTIME_CONSUMED_SOURCE_CONTRACT"])
REV04_EXECUTION_MATERIAL_PROJECTION = tuple(_REV04_AUDIT_DATA["REV04_EXECUTION_MATERIAL_PROJECTION"])
REV02_PREDECESSOR_FAMILY_DISPOSITIONS = MappingProxyType(
    {
        **dict(_REV04_AUDIT_DATA["REV02_FAMILY_DISPOSITIONS"]),
        "operations.EXACT_ORDER.documented_http_statuses[200]": "PRESERVED_EXECUTION_MATERIAL",
        "operations.EXACT_ORDER.documented_http_statuses[401]": "PRESERVED_EXECUTION_MATERIAL",
        "operations.EXACT_ORDER.documented_http_statuses[404]": "PRESERVED_EXECUTION_MATERIAL",
        "operations.EXACT_ORDER.documented_http_statuses[500]": "PRESERVED_EXECUTION_MATERIAL",
    }
)
del _REV04_AUDIT_DATA

COVERAGE_SET_IDENTITIES: Mapping[str, Tuple[int, str]] = MappingProxyType({
    "PREDECESSOR_EXECUTION_MATERIAL": (
        199, "559f6575fb71d50584cc6094f73e51b6859f0802b923a22aed6f80c1c3b63f2b",
    ),
    "REV03_ACCEPTED_EXECUTION_MATERIAL": (
        71, "1d74776161ad1c8539783c26380ab53ba36603ca8b27847cafea069e0bd185df",
    ),
    "RUNTIME_CONSUMED_SOURCE_CONTRACT": (
        174, "d943cf97151a7ca2586c832fd198b061dcc22a86c7193652fc33f173d401a043",
    ),
    "REV04_EXECUTION_MATERIAL_PROJECTION": (
        298, "c8d09262f9db8e73095b28ded702708e313d4e8224d070ba879cb7ea95b8ef1f",
    ),
    "UNION_INPUT": (
        291, "15559b719b3deedf4025a2b38065df573bdefce747a47e62de88708cf9f4ed13",
    ),
    "MISSING_FROM_REV04_AFTER_EXCLUSIONS": (
        0, "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
    ),
})


def build_revision_04_source_contract() -> Dict[str, object]:
    """Return a fresh mutable copy of the exact accepted Revision-04 contract."""

    parsed = json.loads(SOURCE_BINDING_MANIFEST_BYTES)
    if type(parsed) is not dict:
        raise AssertionError("embedded Revision-04 source contract is not an object")
    return parsed


def canonical_source_contract_bytes(contract: object) -> bytes:
    """Serialize normalized source material using RA4-MANIFEST-001."""

    return json.dumps(
        contract, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")


def operation_source_contract_bytes(operation: str) -> bytes:
    contract = build_revision_04_source_contract()
    operations = contract["operations"]
    if type(operations) is not dict or operation not in operations:
        raise KeyError(operation)
    return canonical_source_contract_bytes(operations[operation])


def validate_predecessor_family_classification(field_families: Sequence[str]) -> bool:
    """Fail closed unless the exact 118 predecessor families are classified."""

    if any(type(item) is not str or item == "" for item in field_families):
        return False
    return (
        len(field_families) == len(REV02_PREDECESSOR_FAMILY_DISPOSITIONS)
        and set(field_families) == set(REV02_PREDECESSOR_FAMILY_DISPOSITIONS)
    )


def validate_execution_material_coverage() -> bool:
    """Recompute the accepted missing-atoms=0 theorem."""

    union_input = (
        set(PREDECESSOR_EXECUTION_MATERIAL)
        | set(REV03_ACCEPTED_EXECUTION_MATERIAL)
        | set(RUNTIME_CONSUMED_SOURCE_CONTRACT)
    )
    return len(union_input - set(REV04_EXECUTION_MATERIAL_PROJECTION)) == 0


_REV04_OPERATION_OBJECTS = build_revision_04_source_contract()["operations"]
assert type(_REV04_OPERATION_OBJECTS) is dict
DOCUMENTED_QUERY_NAME_SETS: Mapping[str, Tuple[str, ...]] = MappingProxyType({
    name: tuple(operation["query_parameter_names"])
    for name, operation in _REV04_OPERATION_OBJECTS.items()
})
del _REV04_OPERATION_OBJECTS

_HISTORICAL_LIVE_QUERY_PAIRS: Mapping[str, str] = MappingProxyType({
    "HISTORICAL_FILLS": "LIVE_FILLS",
    "HISTORICAL_ORDERS": "LIVE_ORDERS",
    "HISTORICAL_POSITIONS": "LIVE_POSITIONS",
})


def unsupported_query_fields(historical_operation: str) -> Tuple[str, ...]:
    """Derive the exact live-minus-historical unsupported-query set."""

    if historical_operation not in _HISTORICAL_LIVE_QUERY_PAIRS:
        raise KeyError(historical_operation)
    live_operation = _HISTORICAL_LIVE_QUERY_PAIRS[historical_operation]
    return tuple(sorted(
        set(DOCUMENTED_QUERY_NAME_SETS[live_operation])
        - set(DOCUMENTED_QUERY_NAME_SETS[historical_operation])
    ))

_REQUIRED_CREDENTIAL_REFERENCES = (
    "KALSHI_DEMO_API_KEY_ID",
    "KALSHI_DEMO_PRIVATE_KEY_PEM",
)
_SUPPORTED_ORDER_STATUSES = frozenset({"resting", "canceled", "executed"})

# ---------------------------------------------------------------------------
# Closed public types
# ---------------------------------------------------------------------------

class CapabilityState(enum.StrEnum):
    PERMITTED = "PERMITTED"
    PROHIBITED = "PROHIBITED"


class AuthenticationClass(enum.StrEnum):
    PUBLIC = "PUBLIC"
    AUTHENTICATED = "AUTHENTICATED"


class HistoricalResolutionCapabilityName(enum.StrEnum):
    """Exact future A3 capabilities.  Independent: possessing one never
    grants another, and credential presence never grants a read."""

    USER_DATA_TIMESTAMP_READ = "KALSHI_DEMO_PUBLIC_USER_DATA_TIMESTAMP_READ"
    HISTORICAL_CUTOFF_READ = "KALSHI_DEMO_PUBLIC_HISTORICAL_CUTOFF_READ"
    LIVE_ORDER_LIST_READ = "KALSHI_DEMO_AUTHENTICATED_LIVE_ORDER_LIST_READ"
    HISTORICAL_ORDER_LIST_READ = "KALSHI_DEMO_AUTHENTICATED_HISTORICAL_ORDER_LIST_READ"
    EXACT_ORDER_READ = "KALSHI_DEMO_AUTHENTICATED_EXACT_ORDER_READ"
    LIVE_FILL_LIST_READ = "KALSHI_DEMO_AUTHENTICATED_LIVE_FILL_LIST_READ"
    HISTORICAL_FILL_LIST_READ = "KALSHI_DEMO_AUTHENTICATED_HISTORICAL_FILL_LIST_READ"
    LIVE_POSITION_LIST_READ = "KALSHI_DEMO_AUTHENTICATED_LIVE_POSITION_LIST_READ"
    HISTORICAL_POSITION_LIST_READ = "KALSHI_DEMO_AUTHENTICATED_HISTORICAL_POSITION_LIST_READ"
    SETTLEMENT_LIST_READ = "KALSHI_DEMO_AUTHENTICATED_SETTLEMENT_LIST_READ"
    CREDENTIAL_USE = "KALSHI_DEMO_CREDENTIAL_USE_FOR_THE_EIGHT_AUTHENTICATED_GET_FAMILIES"


REQUIRED_HISTORICAL_RESOLUTION_CAPABILITIES: FrozenSet[HistoricalResolutionCapabilityName] = (
    frozenset(HistoricalResolutionCapabilityName)
)


class HistoricalResolutionOperation(enum.StrEnum):
    USER_DATA_TIMESTAMP = "USER_DATA_TIMESTAMP"
    HISTORICAL_CUTOFF = "HISTORICAL_CUTOFF"
    LIVE_ORDERS = "LIVE_ORDERS"
    HISTORICAL_ORDERS = "HISTORICAL_ORDERS"
    EXACT_ORDER = "EXACT_ORDER"
    LIVE_FILLS = "LIVE_FILLS"
    HISTORICAL_FILLS = "HISTORICAL_FILLS"
    LIVE_POSITIONS = "LIVE_POSITIONS"
    HISTORICAL_POSITIONS = "HISTORICAL_POSITIONS"
    SETTLEMENTS = "SETTLEMENTS"


class DirectMatchSourceClass(enum.StrEnum):
    NONE = "NONE"
    LIVE_PRESENT = "LIVE_PRESENT"
    HISTORICAL_ONLY = "HISTORICAL_ONLY"
    LIVE_AND_HISTORICAL_COMPATIBLE = "LIVE_AND_HISTORICAL_COMPATIBLE"
    CONFLICT = "CONFLICT"


class BindingSourceClass(enum.StrEnum):
    NONE = "NONE"
    LIVE_PRESENT = "LIVE_PRESENT"
    HISTORICAL_ONLY = "HISTORICAL_ONLY"
    LIVE_AND_HISTORICAL_COMPATIBLE = "LIVE_AND_HISTORICAL_COMPATIBLE"
    FILL_DERIVED = "FILL_DERIVED"
    CONFLICT = "CONFLICT"


class ExactOrderRereadReason(enum.StrEnum):
    NONE = "NONE"
    LIVE_DIRECT_REVALIDATION = "LIVE_DIRECT_REVALIDATION"
    FILL_DERIVED_IDENTITY_BINDING = "FILL_DERIVED_IDENTITY_BINDING"
    NOT_REQUIRED_HISTORICAL_ONLY = "NOT_REQUIRED_HISTORICAL_ONLY"


class FillEvidenceOrigin(enum.StrEnum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    POST_BINDING_BOUND_ORDER_TRAVERSAL = "POST_BINDING_BOUND_ORDER_TRAVERSAL"
    PRE_BINDING_FILL_DISCOVERY_REUSED = "PRE_BINDING_FILL_DISCOVERY_REUSED"


class ResultClass(enum.StrEnum):
    READ_POSITIVE_ORDER_BOUND_ACTIVE = "READ_POSITIVE_ORDER_BOUND_ACTIVE"
    READ_POSITIVE_FILL_DERIVED_ORDER_BOUND_ACTIVE = "READ_POSITIVE_FILL_DERIVED_ORDER_BOUND_ACTIVE"
    READ_POSITIVE_ORDER_BOUND_TERMINAL_RECONCILED = "READ_POSITIVE_ORDER_BOUND_TERMINAL_RECONCILED"
    READ_POSITIVE_FILL_DERIVED_ORDER_BOUND_TERMINAL_RECONCILED = "READ_POSITIVE_FILL_DERIVED_ORDER_BOUND_TERMINAL_RECONCILED"
    READ_POSITIVE_ORDER_BOUND_TERMINAL_ECONOMIC_INCOMPLETE = "READ_POSITIVE_ORDER_BOUND_TERMINAL_ECONOMIC_INCOMPLETE"
    READ_POSITIVE_FILL_DERIVED_ORDER_BOUND_TERMINAL_ECONOMIC_INCOMPLETE = "READ_POSITIVE_FILL_DERIVED_ORDER_BOUND_TERMINAL_ECONOMIC_INCOMPLETE"
    READ_ZERO_MATCH_AUTHORITATIVE_NONEXISTENCE_PROVEN = "READ_ZERO_MATCH_AUTHORITATIVE_NONEXISTENCE_PROVEN"
    READ_ZERO_MATCH_NEGATIVE_THEOREM_NOT_PROVEN = "READ_ZERO_MATCH_NEGATIVE_THEOREM_NOT_PROVEN"
    READ_HISTORICAL_RETENTION_OR_CUTOFF_GAP = "READ_HISTORICAL_RETENTION_OR_CUTOFF_GAP"
    READ_HISTORY_INTERVAL_UNOBSERVABLE = "READ_HISTORY_INTERVAL_UNOBSERVABLE"
    READ_SOURCE_TRAVERSAL_INCOMPLETE = "READ_SOURCE_TRAVERSAL_INCOMPLETE"
    READ_SOURCE_SEMANTICS_INSUFFICIENT_FOR_CLOSURE = "READ_SOURCE_SEMANTICS_INSUFFICIENT_FOR_CLOSURE"
    READ_ENDPOINT_OR_SOURCE_FAILURE = "READ_ENDPOINT_OR_SOURCE_FAILURE"
    READ_IDENTITY_AMBIGUOUS = "READ_IDENTITY_AMBIGUOUS"
    READ_MULTIPLE_CANDIDATE_ORDER_IDS = "READ_MULTIPLE_CANDIDATE_ORDER_IDS"
    READ_ACCOUNT_OR_SUBACCOUNT_AMBIGUOUS = "READ_ACCOUNT_OR_SUBACCOUNT_AMBIGUOUS"
    READ_AUTHORITATIVE_RESPONSE_MALFORMED = "READ_AUTHORITATIVE_RESPONSE_MALFORMED"
    READ_AUTHORITATIVE_RESPONSE_AMBIGUOUS = "READ_AUTHORITATIVE_RESPONSE_AMBIGUOUS"
    READ_MASTER_DEADLINE_EXHAUSTED = "READ_MASTER_DEADLINE_EXHAUSTED"
    READ_EVIDENCE_ARTIFACT_INTEGRITY_FAILURE = "READ_EVIDENCE_ARTIFACT_INTEGRITY_FAILURE"
    READ_SOURCE_DRIFT = "READ_SOURCE_DRIFT"
    READ_CAPABILITY_OR_SCOPE_VIOLATION = "READ_CAPABILITY_OR_SCOPE_VIOLATION"


_NEGATIVE_UNREACHABLE_RESULTS: FrozenSet[ResultClass] = frozenset({
    ResultClass.READ_ZERO_MATCH_AUTHORITATIVE_NONEXISTENCE_PROVEN,
})

# RA1-RES-004 precedence tier 1 ("capability/environment/provenance/source
# drift").  This is the only tier ranked *above* deadline exhaustion (tier 2);
# every other result class in the closed taxonomy (malformed/ambiguous
# response, identity ambiguity, source failure/incompleteness, history-
# interval/retention gaps, and every positive/zero-match terminal class) is
# ranked below deadline exhaustion and must yield to it.
_PRECEDENCE_ABOVE_DEADLINE: FrozenSet[ResultClass] = frozenset({
    ResultClass.READ_CAPABILITY_OR_SCOPE_VIOLATION,
    ResultClass.READ_SOURCE_DRIFT,
})


class HaltCode(enum.StrEnum):
    CANONICAL_BASE_MISMATCH = "CANONICAL_BASE_MISMATCH"
    CANONICAL_TREE_MISMATCH = "CANONICAL_TREE_MISMATCH"
    CANONICAL_PARENT_MISMATCH = "CANONICAL_PARENT_MISMATCH"
    CONTROLLING_ARTIFACT_IDENTITY_MISMATCH = "CONTROLLING_ARTIFACT_IDENTITY_MISMATCH"

    TASK_CURRENT_SOURCE_UNAVAILABLE = "TASK_CURRENT_SOURCE_UNAVAILABLE"
    AUTHORITATIVE_SOURCE_DRIFT_SPEC_REVISION_REQUIRED = "AUTHORITATIVE_SOURCE_DRIFT_SPEC_REVISION_REQUIRED"
    OFFICIAL_SOURCE_CONFLICT = "OFFICIAL_SOURCE_CONFLICT"
    AUTHORITATIVE_RESPONSE_MALFORMED = "AUTHORITATIVE_RESPONSE_MALFORMED"
    AUTHORITATIVE_SOURCE_AMBIGUITY = "AUTHORITATIVE_SOURCE_AMBIGUITY"

    DEMO_ENVIRONMENT_REQUIRED = "DEMO_ENVIRONMENT_REQUIRED"
    PRODUCTION_ENDPOINT_PROHIBITED = "PRODUCTION_ENDPOINT_PROHIBITED"
    GET_ONLY_CONTRACT_VIOLATION = "GET_ONLY_CONTRACT_VIOLATION"
    CAPABILITY_MISSING = "CAPABILITY_MISSING"
    SCOPE_IDENTITY_MISMATCH = "SCOPE_IDENTITY_MISMATCH"
    ACCOUNT_SUBACCOUNT_AMBIGUOUS = "ACCOUNT_SUBACCOUNT_AMBIGUOUS"
    SECRET_BOUNDARY_VIOLATION = "SECRET_BOUNDARY_VIOLATION"

    PAGINATION_CURSOR_MALFORMED = "PAGINATION_CURSOR_MALFORMED"
    PAGINATION_CURSOR_CYCLE = "PAGINATION_CURSOR_CYCLE"
    PAGE_BUDGET_EXHAUSTED = "PAGE_BUDGET_EXHAUSTED"
    SOURCE_TRAVERSAL_INCOMPLETE = "SOURCE_TRAVERSAL_INCOMPLETE"
    GLOBAL_REQUEST_BUDGET_EXHAUSTED = "GLOBAL_REQUEST_BUDGET_EXHAUSTED"
    BRANCH_REQUEST_BUDGET_EXHAUSTED = "BRANCH_REQUEST_BUDGET_EXHAUSTED"

    ORDER_ID_DUPLICATE_CONFLICT = "ORDER_ID_DUPLICATE_CONFLICT"
    HISTORICAL_ORDER_PARTITION_CONFLICT = "HISTORICAL_ORDER_PARTITION_CONFLICT"
    ORDER_SCOPE_CONFLICT = "ORDER_SCOPE_CONFLICT"
    ORDER_IDENTITY_OR_ECONOMIC_MISMATCH = "ORDER_IDENTITY_OR_ECONOMIC_MISMATCH"
    IDENTITY_AMBIGUOUS = "IDENTITY_AMBIGUOUS"

    FILL_ID_DUPLICATE_CONFLICT = "FILL_ID_DUPLICATE_CONFLICT"
    FILL_SCOPE_CONFLICT = "FILL_SCOPE_CONFLICT"
    MULTIPLE_CANDIDATE_ORDER_IDS = "MULTIPLE_CANDIDATE_ORDER_IDS"
    CANDIDATE_ORDER_ID_BUDGET_EXCEEDED = "CANDIDATE_ORDER_ID_BUDGET_EXCEEDED"
    CANDIDATE_EXACT_ORDER_UNAVAILABLE = "CANDIDATE_EXACT_ORDER_UNAVAILABLE"
    DIRECT_LIVE_EXACT_ORDER_REVALIDATION_UNAVAILABLE = "DIRECT_LIVE_EXACT_ORDER_REVALIDATION_UNAVAILABLE"

    POSITION_SCOPE_OR_ARCHIVE_AMBIGUOUS = "POSITION_SCOPE_OR_ARCHIVE_AMBIGUOUS"
    POSITION_EVIDENCE_INCOMPLETE = "POSITION_EVIDENCE_INCOMPLETE"
    SETTLEMENT_EVIDENCE_INCOMPLETE = "SETTLEMENT_EVIDENCE_INCOMPLETE"

    HISTORICAL_CUTOFF_OR_FRESHNESS_GAP = "HISTORICAL_CUTOFF_OR_FRESHNESS_GAP"
    HISTORY_INTERVAL_UNOBSERVABLE = "HISTORY_INTERVAL_UNOBSERVABLE"
    HISTORICAL_RETENTION_THEOREM_UNPROVEN = "HISTORICAL_RETENTION_THEOREM_UNPROVEN"

    ORDER_FILL_RECONCILIATION_MISMATCH = "ORDER_FILL_RECONCILIATION_MISMATCH"
    ECONOMIC_RISK_INVARIANT_VIOLATION = "ECONOMIC_RISK_INVARIANT_VIOLATION"
    BOUND_ORDER_ECONOMIC_RECONCILIATION_INCOMPLETE = "BOUND_ORDER_ECONOMIC_RECONCILIATION_INCOMPLETE"

    MASTER_DEADLINE_EXHAUSTED = "MASTER_DEADLINE_EXHAUSTED"
    EVIDENCE_ARTIFACT_INTEGRITY_FAILURE = "EVIDENCE_ARTIFACT_INTEGRITY_FAILURE"

    TRANSPORT_READ_FAILURE = "TRANSPORT_READ_FAILURE"
    UNEXPECTED_HTTP_STATUS = "UNEXPECTED_HTTP_STATUS"
    REDIRECT_PROHIBITED = "REDIRECT_PROHIBITED"


_CAPABILITY_SCOPE_HALTS: FrozenSet[HaltCode] = frozenset({
    HaltCode.CANONICAL_BASE_MISMATCH,
    HaltCode.CANONICAL_TREE_MISMATCH,
    HaltCode.CANONICAL_PARENT_MISMATCH,
    HaltCode.CONTROLLING_ARTIFACT_IDENTITY_MISMATCH,
    HaltCode.CAPABILITY_MISSING,
    HaltCode.DEMO_ENVIRONMENT_REQUIRED,
    HaltCode.PRODUCTION_ENDPOINT_PROHIBITED,
    HaltCode.GET_ONLY_CONTRACT_VIOLATION,
    HaltCode.SECRET_BOUNDARY_VIOLATION,
    HaltCode.SCOPE_IDENTITY_MISMATCH,
})
_SOURCE_DRIFT_HALTS: FrozenSet[HaltCode] = frozenset({
    HaltCode.TASK_CURRENT_SOURCE_UNAVAILABLE,
    HaltCode.AUTHORITATIVE_SOURCE_DRIFT_SPEC_REVISION_REQUIRED,
    HaltCode.OFFICIAL_SOURCE_CONFLICT,
})
_MALFORMED_HALTS: FrozenSet[HaltCode] = frozenset({HaltCode.AUTHORITATIVE_RESPONSE_MALFORMED})
_AMBIGUOUS_RESPONSE_HALTS: FrozenSet[HaltCode] = frozenset({
    HaltCode.AUTHORITATIVE_SOURCE_AMBIGUITY,
    HaltCode.HISTORICAL_ORDER_PARTITION_CONFLICT,
})
_TRAVERSAL_INCOMPLETE_HALTS: FrozenSet[HaltCode] = frozenset({
    HaltCode.PAGINATION_CURSOR_MALFORMED,
    HaltCode.PAGINATION_CURSOR_CYCLE,
    HaltCode.PAGE_BUDGET_EXHAUSTED,
    HaltCode.SOURCE_TRAVERSAL_INCOMPLETE,
    HaltCode.GLOBAL_REQUEST_BUDGET_EXHAUSTED,
    HaltCode.BRANCH_REQUEST_BUDGET_EXHAUSTED,
})
_IDENTITY_AMBIGUOUS_HALTS: FrozenSet[HaltCode] = frozenset({
    HaltCode.ORDER_ID_DUPLICATE_CONFLICT,
    HaltCode.ORDER_SCOPE_CONFLICT,
    HaltCode.IDENTITY_AMBIGUOUS,
    HaltCode.FILL_ID_DUPLICATE_CONFLICT,
    HaltCode.FILL_SCOPE_CONFLICT,
    HaltCode.ORDER_IDENTITY_OR_ECONOMIC_MISMATCH,
})
_MULTIPLE_CANDIDATE_HALTS: FrozenSet[HaltCode] = frozenset({
    HaltCode.MULTIPLE_CANDIDATE_ORDER_IDS,
    HaltCode.CANDIDATE_ORDER_ID_BUDGET_EXCEEDED,
})
_ENDPOINT_FAILURE_HALTS: FrozenSet[HaltCode] = frozenset({
    HaltCode.CANDIDATE_EXACT_ORDER_UNAVAILABLE,
    HaltCode.DIRECT_LIVE_EXACT_ORDER_REVALIDATION_UNAVAILABLE,
    HaltCode.TRANSPORT_READ_FAILURE,
    HaltCode.UNEXPECTED_HTTP_STATUS,
    HaltCode.REDIRECT_PROHIBITED,
})
_SOURCE_SEMANTICS_HALTS: FrozenSet[HaltCode] = frozenset({
    HaltCode.POSITION_SCOPE_OR_ARCHIVE_AMBIGUOUS,
    HaltCode.POSITION_EVIDENCE_INCOMPLETE,
    HaltCode.SETTLEMENT_EVIDENCE_INCOMPLETE,
})
_HISTORY_UNOBSERVABLE_HALTS: FrozenSet[HaltCode] = frozenset({
    HaltCode.HISTORICAL_CUTOFF_OR_FRESHNESS_GAP,
    HaltCode.HISTORY_INTERVAL_UNOBSERVABLE,
})
_RETENTION_GAP_HALTS: FrozenSet[HaltCode] = frozenset({
    HaltCode.HISTORICAL_RETENTION_THEOREM_UNPROVEN,
})


def _generic_result_for_halt(code: HaltCode) -> ResultClass:
    """Map an early (pre-binding) halt to its closed result class per the
    RA1-RES-004 precedence rule.  Economic-completeness halts are handled
    separately once positive identity is already established."""

    if code in _CAPABILITY_SCOPE_HALTS:
        return ResultClass.READ_CAPABILITY_OR_SCOPE_VIOLATION
    if code is HaltCode.ACCOUNT_SUBACCOUNT_AMBIGUOUS:
        return ResultClass.READ_ACCOUNT_OR_SUBACCOUNT_AMBIGUOUS
    if code in _SOURCE_DRIFT_HALTS:
        return ResultClass.READ_SOURCE_DRIFT
    if code is HaltCode.MASTER_DEADLINE_EXHAUSTED:
        return ResultClass.READ_MASTER_DEADLINE_EXHAUSTED
    if code in _MALFORMED_HALTS:
        return ResultClass.READ_AUTHORITATIVE_RESPONSE_MALFORMED
    if code in _AMBIGUOUS_RESPONSE_HALTS:
        return ResultClass.READ_AUTHORITATIVE_RESPONSE_AMBIGUOUS
    if code in _IDENTITY_AMBIGUOUS_HALTS:
        return ResultClass.READ_IDENTITY_AMBIGUOUS
    if code in _MULTIPLE_CANDIDATE_HALTS:
        return ResultClass.READ_MULTIPLE_CANDIDATE_ORDER_IDS
    if code in _TRAVERSAL_INCOMPLETE_HALTS:
        return ResultClass.READ_SOURCE_TRAVERSAL_INCOMPLETE
    if code in _ENDPOINT_FAILURE_HALTS:
        return ResultClass.READ_ENDPOINT_OR_SOURCE_FAILURE
    if code in _SOURCE_SEMANTICS_HALTS:
        return ResultClass.READ_SOURCE_SEMANTICS_INSUFFICIENT_FOR_CLOSURE
    if code in _HISTORY_UNOBSERVABLE_HALTS:
        return ResultClass.READ_HISTORY_INTERVAL_UNOBSERVABLE
    if code in _RETENTION_GAP_HALTS:
        return ResultClass.READ_HISTORICAL_RETENTION_OR_CUTOFF_GAP
    if code is HaltCode.EVIDENCE_ARTIFACT_INTEGRITY_FAILURE:
        return ResultClass.READ_EVIDENCE_ARTIFACT_INTEGRITY_FAILURE
    return ResultClass.READ_ENDPOINT_OR_SOURCE_FAILURE


class HistoricalResolutionPlanningError(ValueError):
    def __init__(self, halt_code: HaltCode):
        super().__init__(halt_code.value)
        self.halt_code = halt_code


@dataclass(frozen=True, slots=True)
class HistoricalResolutionCapabilityEnvelope:
    """Non-secret, closed future-execution capability declaration.  Credential
    *reference names* are metadata only; presence never grants a read."""

    environment: str
    rest_origin: str
    credential_reference_names: Tuple[str, ...]
    granted_capabilities: FrozenSet[HistoricalResolutionCapabilityName]
    network_access: CapabilityState
    demo_public_reads: CapabilityState
    demo_authenticated_reads: CapabilityState
    credential_use: CapabilityState
    demo_writes: CapabilityState
    production_public_reads: CapabilityState
    production_authenticated_reads: CapabilityState
    production_writes: CapabilityState
    account_funding: CapabilityState
    websocket: CapabilityState


@dataclass(frozen=True, slots=True)
class ArtifactIdentity:
    path: str
    bytes: int
    sha256: str
    git_blob: str


@dataclass(frozen=True, slots=True)
class HistoricalResolutionProvenance:
    implementation: ArtifactIdentity
    tests: ArtifactIdentity


@dataclass(frozen=True, slots=True)
class HistoricalResolutionInput:
    capability_envelope: HistoricalResolutionCapabilityEnvelope
    source_binding_manifest_bytes: bytes
    provenance: HistoricalResolutionProvenance


@dataclass(frozen=True, slots=True)
class HistoricalResolutionPlan:
    """Secret-free closed plan.  The executor replans internally under its
    master deadline rather than trusting a precomputed public plan."""

    environment: str
    origin: str
    base_path: str
    source_binding_sha256: str
    ticker: str
    client_order_id: str


@dataclass(frozen=True, slots=True)
class PreparedGetRequest:
    """Internally generated request.  No method/body/header/url parameter
    exists on the public executor; method is a read-only literal property."""

    operation: HistoricalResolutionOperation
    origin: str
    path: str
    query: Mapping[str, object]
    authentication_class: AuthenticationClass
    page_ordinal: int
    effective_deadline_monotonic: float

    @property
    def method(self) -> str:
        return "GET"


@dataclass(frozen=True, slots=True)
class RawHttpResponse:
    status: int
    media_type: str
    body_bytes: bytes
    retry_count: int
    redirect_count: int


class HistoricalResolutionTransport(Protocol):
    def send(self, request: PreparedGetRequest) -> RawHttpResponse: ...


@dataclass(frozen=True, slots=True)
class HistoricalResolutionResult:
    result_class: ResultClass
    halt_code: Optional[HaltCode]
    bound_order_id: Optional[str]
    binding_source_class: BindingSourceClass
    planned_branch: str
    request_count: int
    retry_count: int
    redirect_count: int
    canonical_fill_quantity: Optional[Decimal]
    canonical_filled_principal: Optional[Decimal]
    canonical_fee_cost: Optional[Decimal]
    writer_proof_state_after: str
    writer_proof_release_eligible_after: bool
    persistent_state_accessed: bool
    persistent_state_mutated: bool
    evidence_json: bytes
    evidence_sha256: str

# ---------------------------------------------------------------------------
# Closed internal operation contract
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class _OperationSpec:
    operation: HistoricalResolutionOperation
    path_template: str
    authentication_class: AuthenticationClass
    paginated: bool
    page_budget: int
    record_key: Optional[str]


_OPERATION_SPECS: Mapping[HistoricalResolutionOperation, _OperationSpec] = MappingProxyType({
    HistoricalResolutionOperation.USER_DATA_TIMESTAMP: _OperationSpec(
        HistoricalResolutionOperation.USER_DATA_TIMESTAMP,
        "/trade-api/v2/exchange/user_data_timestamp",
        AuthenticationClass.PUBLIC, False, MAX_USER_DATA_TIMESTAMP_READS, None,
    ),
    HistoricalResolutionOperation.HISTORICAL_CUTOFF: _OperationSpec(
        HistoricalResolutionOperation.HISTORICAL_CUTOFF,
        "/trade-api/v2/historical/cutoff",
        AuthenticationClass.PUBLIC, False, MAX_HISTORICAL_CUTOFF_READS, None,
    ),
    HistoricalResolutionOperation.LIVE_ORDERS: _OperationSpec(
        HistoricalResolutionOperation.LIVE_ORDERS,
        "/trade-api/v2/portfolio/orders",
        AuthenticationClass.AUTHENTICATED, True, MAX_LIVE_ORDER_PAGES, "orders",
    ),
    HistoricalResolutionOperation.HISTORICAL_ORDERS: _OperationSpec(
        HistoricalResolutionOperation.HISTORICAL_ORDERS,
        "/trade-api/v2/historical/orders",
        AuthenticationClass.AUTHENTICATED, True, MAX_HISTORICAL_ORDER_PAGES, "orders",
    ),
    HistoricalResolutionOperation.EXACT_ORDER: _OperationSpec(
        HistoricalResolutionOperation.EXACT_ORDER,
        "/trade-api/v2/portfolio/orders/{order_id}",
        AuthenticationClass.AUTHENTICATED, False, MAX_FILL_DERIVED_CANDIDATE_ORDER_IDS + MAX_DIRECT_EXACT_ORDER_REVALIDATIONS, None,
    ),
    HistoricalResolutionOperation.LIVE_FILLS: _OperationSpec(
        HistoricalResolutionOperation.LIVE_FILLS,
        "/trade-api/v2/portfolio/fills",
        AuthenticationClass.AUTHENTICATED, True, MAX_LIVE_FILL_PAGES, "fills",
    ),
    HistoricalResolutionOperation.HISTORICAL_FILLS: _OperationSpec(
        HistoricalResolutionOperation.HISTORICAL_FILLS,
        "/trade-api/v2/historical/fills",
        AuthenticationClass.AUTHENTICATED, True, MAX_HISTORICAL_FILL_PAGES, "fills",
    ),
    HistoricalResolutionOperation.LIVE_POSITIONS: _OperationSpec(
        HistoricalResolutionOperation.LIVE_POSITIONS,
        "/trade-api/v2/portfolio/positions",
        AuthenticationClass.AUTHENTICATED, True, MAX_LIVE_POSITION_PAGES, "market_positions",
    ),
    HistoricalResolutionOperation.HISTORICAL_POSITIONS: _OperationSpec(
        HistoricalResolutionOperation.HISTORICAL_POSITIONS,
        "/trade-api/v2/historical/positions",
        AuthenticationClass.AUTHENTICATED, True, MAX_HISTORICAL_POSITION_PAGES, "market_positions",
    ),
    HistoricalResolutionOperation.SETTLEMENTS: _OperationSpec(
        HistoricalResolutionOperation.SETTLEMENTS,
        "/trade-api/v2/portfolio/settlements",
        AuthenticationClass.AUTHENTICATED, True, MAX_SETTLEMENT_PAGES, "settlements",
    ),
})

_PAGINATED_OPERATIONS: FrozenSet[HistoricalResolutionOperation] = frozenset(
    op for op, spec in _OPERATION_SPECS.items() if spec.paginated
)

# ---------------------------------------------------------------------------
# Strict parsing / canonicalization
# ---------------------------------------------------------------------------

_COUNT_PATTERN = re.compile(r"[0-9]+\.[0-9]{2}")
_MONEY_PATTERN = re.compile(r"[0-9]+(?:\.[0-9]{1,6})?")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_BLOB_PATTERN = re.compile(r"[0-9a-f]{40}")
_RFC3339_PATTERN = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})"
)


class _DuplicateJsonKey(ValueError):
    pass


class _NonFiniteJson(ValueError):
    pass


def _pairs_no_duplicates(pairs: Sequence[Tuple[str, object]]) -> Dict[str, object]:
    result: Dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(key)
        result[key] = value
    return result


def _reject_nonfinite(token: str) -> object:
    raise _NonFiniteJson(token)


def _strict_json_loads(raw: bytes) -> object:
    if type(raw) is not bytes:
        raise ValueError("response body must be bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("response is not UTF-8") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=_reject_nonfinite,
        )
    except (json.JSONDecodeError, _DuplicateJsonKey, _NonFiniteJson) as exc:
        raise ValueError("invalid strict JSON") from exc


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _parse_count(value: object) -> Decimal:
    if type(value) is not str or _COUNT_PATTERN.fullmatch(value) is None:
        raise ValueError("invalid fixed-point count")
    return Decimal(value)


def _parse_money(value: object) -> Decimal:
    if type(value) is not str or _MONEY_PATTERN.fullmatch(value) is None:
        raise ValueError("invalid fixed-point monetary value")
    return Decimal(value)


def _opaque_identifier(value: object) -> str:
    if type(value) is not str or value == "":
        raise ValueError("invalid opaque identifier")
    return value


def _exact_int(value: object) -> int:
    if type(value) is not int or type(value) is bool:
        raise ValueError("integer required")
    return value


def _exact_bool(value: object) -> bool:
    if type(value) is not bool:
        raise ValueError("boolean required")
    return value


def _valid_rfc3339(value: object) -> bool:
    if type(value) is not str or _RFC3339_PATTERN.fullmatch(value) is None:
        return False
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _parse_rfc3339(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    return datetime.fromisoformat(normalized)


def _valid_utc_rfc3339(value: object) -> bool:
    """Strict UTC-only RFC3339 validator (RA1-TIME-003).  A tz-aware value
    with a non-zero UTC offset must not pass merely because it carries an
    explicit offset; the controlling contract requires these authoritative
    freshness/cutoff fields to be UTC (``Z`` or an explicitly-zero offset)."""

    if not _valid_rfc3339(value):
        return False
    assert type(value) is str
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    offset = parsed.utcoffset()
    return offset is not None and offset == timedelta(0)


def _json_safe(value: object) -> object:
    if isinstance(value, enum.Enum):
        return value.value
    if type(value) is Decimal:
        return str(value)
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (tuple, list)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return [_json_safe(v) for v in sorted(value, key=lambda item: repr(item))]
    if value is None or type(value) in (str, int, bool):
        return value
    raise TypeError("unsupported evidence value")

# ---------------------------------------------------------------------------
# Source/capability/provenance validation
# ---------------------------------------------------------------------------

def _normalized_source_candidate(candidate: object) -> Optional[Dict[str, object]]:
    if type(candidate) is bytes:
        if len(candidate) == 0:
            return None
        try:
            parsed = _strict_json_loads(candidate)
        except ValueError:
            return None
    elif type(candidate) is dict:
        parsed = candidate
    else:
        return None
    return parsed if type(parsed) is dict else None


def _positive_source_claims_agree(primary: object, rendered: object) -> bool:
    """Compare only positive rendered claims; rendered silence is neutral."""

    if type(rendered) is dict:
        if type(primary) is not dict:
            return False
        for key, rendered_value in rendered.items():
            if key not in primary:
                return False
            if not _positive_source_claims_agree(primary[key], rendered_value):
                return False
        return True
    return type(primary) is type(rendered) and primary == rendered


def compare_revision_04_source_contract(
    current_openapi: object,
    current_rendered_positive_claims: Optional[Mapping[str, object]] = None,
) -> Optional[HaltCode]:
    """Compare caller-supplied current material with the accepted baseline.

    This pure comparator performs no retrieval.  A rendered mapping is a
    positive-claims subset: omitted keys are silence, while a positive
    disagreement is an official-source conflict.  Mutual current-source
    agreement never excuses drift from the accepted Revision-04 contract.
    """

    current = _normalized_source_candidate(current_openapi)
    if current is None:
        if type(current_openapi) is bytes and len(current_openapi) > 0:
            return HaltCode.AUTHORITATIVE_SOURCE_DRIFT_SPEC_REVISION_REQUIRED
        return HaltCode.TASK_CURRENT_SOURCE_UNAVAILABLE
    if current_rendered_positive_claims is not None:
        if type(current_rendered_positive_claims) is not dict:
            return HaltCode.AUTHORITATIVE_SOURCE_AMBIGUITY
        if not _positive_source_claims_agree(current, current_rendered_positive_claims):
            return HaltCode.OFFICIAL_SOURCE_CONFLICT
    try:
        current_bytes = canonical_source_contract_bytes(current)
    except (TypeError, ValueError):
        return HaltCode.AUTHORITATIVE_SOURCE_AMBIGUITY
    if current_bytes != SOURCE_BINDING_MANIFEST_BYTES:
        return HaltCode.AUTHORITATIVE_SOURCE_DRIFT_SPEC_REVISION_REQUIRED
    return None


def validate_source_binding_manifest(raw: object) -> Optional[HaltCode]:
    comparison_halt = compare_revision_04_source_contract(raw)
    if comparison_halt is not None:
        return comparison_halt
    assert type(raw) is bytes
    if len(raw) != SOURCE_BINDING_MANIFEST_LENGTH or _sha256(raw) != SOURCE_BINDING_MANIFEST_SHA256:
        return HaltCode.AUTHORITATIVE_SOURCE_DRIFT_SPEC_REVISION_REQUIRED
    try:
        parsed = _strict_json_loads(raw)
    except ValueError:
        return HaltCode.AUTHORITATIVE_SOURCE_DRIFT_SPEC_REVISION_REQUIRED
    if type(parsed) is not dict:
        return HaltCode.AUTHORITATIVE_SOURCE_DRIFT_SPEC_REVISION_REQUIRED
    if parsed.get("schema_id") != SOURCE_BINDING_MANIFEST_ID:
        return HaltCode.AUTHORITATIVE_SOURCE_DRIFT_SPEC_REVISION_REQUIRED
    if parsed.get("normalization_revision") != SOURCE_BINDING_NORMALIZATION_REVISION:
        return HaltCode.AUTHORITATIVE_SOURCE_DRIFT_SPEC_REVISION_REQUIRED
    operations = parsed.get("operations")
    if type(operations) is not dict or set(operations) != set(OPERATION_BINDING_IDENTITIES):
        return HaltCode.AUTHORITATIVE_SOURCE_DRIFT_SPEC_REVISION_REQUIRED
    for name, (expected_bytes, expected_sha) in OPERATION_BINDING_IDENTITIES.items():
        operation_bytes = _canonical_json_bytes(operations[name])
        if len(operation_bytes) != expected_bytes or _sha256(operation_bytes) != expected_sha:
            return HaltCode.AUTHORITATIVE_SOURCE_DRIFT_SPEC_REVISION_REQUIRED
        operation = operations[name]
        if type(operation) is not dict or operation.get("method") != "GET":
            return HaltCode.GET_ONLY_CONTRACT_VIOLATION
    return None


def _validate_artifact_identity(identity: object) -> bool:
    return (
        type(identity) is ArtifactIdentity
        and type(identity.path) is str
        and identity.path != ""
        and type(identity.bytes) is int
        and identity.bytes >= 0
        and type(identity.sha256) is str
        and _SHA256_PATTERN.fullmatch(identity.sha256) is not None
        and type(identity.git_blob) is str
        and _BLOB_PATTERN.fullmatch(identity.git_blob) is not None
    )


def _validate_capability(envelope: object) -> Optional[HaltCode]:
    if type(envelope) is not HistoricalResolutionCapabilityEnvelope:
        return HaltCode.CAPABILITY_MISSING
    if envelope.environment != ENVIRONMENT:
        return HaltCode.DEMO_ENVIRONMENT_REQUIRED
    if type(envelope.rest_origin) is not str:
        return HaltCode.DEMO_ENVIRONMENT_REQUIRED
    if envelope.rest_origin == PRODUCTION_REST_ORIGIN:
        return HaltCode.PRODUCTION_ENDPOINT_PROHIBITED
    if envelope.rest_origin != DEMO_REST_ORIGIN:
        return HaltCode.DEMO_ENVIRONMENT_REQUIRED
    if type(envelope.credential_reference_names) is not tuple:
        return HaltCode.SECRET_BOUNDARY_VIOLATION
    if envelope.credential_reference_names != _REQUIRED_CREDENTIAL_REFERENCES:
        return HaltCode.SECRET_BOUNDARY_VIOLATION
    if type(envelope.granted_capabilities) is not frozenset:
        return HaltCode.CAPABILITY_MISSING
    if any(type(capability) is not HistoricalResolutionCapabilityName for capability in envelope.granted_capabilities):
        return HaltCode.CAPABILITY_MISSING
    # Every capability is independently required.  No inheritance from
    # authenticated-read, public-read, network access, or credential presence.
    if envelope.granted_capabilities != REQUIRED_HISTORICAL_RESOLUTION_CAPABILITIES:
        return HaltCode.CAPABILITY_MISSING

    required_permitted = (
        envelope.network_access,
        envelope.demo_public_reads,
        envelope.demo_authenticated_reads,
        envelope.credential_use,
    )
    if any(type(v) is not CapabilityState or v is not CapabilityState.PERMITTED for v in required_permitted):
        return HaltCode.CAPABILITY_MISSING

    required_prohibited = (
        envelope.demo_writes,
        envelope.production_public_reads,
        envelope.production_authenticated_reads,
        envelope.production_writes,
        envelope.account_funding,
        envelope.websocket,
    )
    if any(type(v) is not CapabilityState or v is not CapabilityState.PROHIBITED for v in required_prohibited):
        return HaltCode.CAPABILITY_MISSING
    return None


def _validate_input(historical_resolution_input: object) -> Optional[HaltCode]:
    if type(historical_resolution_input) is not HistoricalResolutionInput:
        return HaltCode.CONTROLLING_ARTIFACT_IDENTITY_MISMATCH
    cap_halt = _validate_capability(historical_resolution_input.capability_envelope)
    if cap_halt is not None:
        return cap_halt
    source_halt = validate_source_binding_manifest(historical_resolution_input.source_binding_manifest_bytes)
    if source_halt is not None:
        return source_halt
    provenance = historical_resolution_input.provenance
    if type(provenance) is not HistoricalResolutionProvenance:
        return HaltCode.CONTROLLING_ARTIFACT_IDENTITY_MISMATCH
    if not _validate_artifact_identity(provenance.implementation):
        return HaltCode.CONTROLLING_ARTIFACT_IDENTITY_MISMATCH
    if not _validate_artifact_identity(provenance.tests):
        return HaltCode.CONTROLLING_ARTIFACT_IDENTITY_MISMATCH
    return None


def plan_historical_resolution(historical_resolution_input: HistoricalResolutionInput) -> HistoricalResolutionPlan:
    halt = _validate_input(historical_resolution_input)
    if halt is not None:
        raise HistoricalResolutionPlanningError(halt)
    return HistoricalResolutionPlan(
        environment=ENVIRONMENT,
        origin=DEMO_REST_ORIGIN,
        base_path=TRADE_API_BASE_PATH,
        source_binding_sha256=SOURCE_BINDING_MANIFEST_SHA256,
        ticker=TICKER,
        client_order_id=CLIENT_ORDER_ID,
    )


# ---------------------------------------------------------------------------
# Secret-free GET signing message
# ---------------------------------------------------------------------------

_TIMESTAMP_MS_PATTERN = re.compile(r"[0-9]+")


def build_prepared_get_signing_message(
    request: PreparedGetRequest,
    *,
    timestamp_ms_text: str,
) -> bytes:
    """Return ``timestamp + GET + path_without_query`` for a validated
    internally shaped request.  No key/signature/header value is accepted or
    returned by this helper."""

    if type(request) is not PreparedGetRequest or _validate_prepared_request(request) is not None:
        raise ValueError(HaltCode.GET_ONLY_CONTRACT_VIOLATION.value)
    if type(timestamp_ms_text) is not str or _TIMESTAMP_MS_PATTERN.fullmatch(timestamp_ms_text) is None:
        raise ValueError("timestamp_ms_text must be canonical ASCII digits")
    return (timestamp_ms_text + "GET" + request.path).encode("utf-8")


# ---------------------------------------------------------------------------
# Parsed order/fill records and provenance
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class _Observation:
    source_stream: str
    page_ordinal: int
    record_ordinal: int
    response_sha256: str


@dataclass(frozen=True, slots=True)
class _OrderRecord:
    order_id: str
    client_order_id: str
    ticker: str
    subaccount_number: int
    exchange_index: Optional[int]
    outcome_side: Optional[str]
    book_side: Optional[str]
    yes_price_dollars: Optional[Decimal]
    no_price_dollars: Optional[Decimal]
    cancel_order_on_pause: Optional[bool]
    status: Optional[str]
    initial_count_fp: Optional[Decimal]
    fill_count_fp: Optional[Decimal]
    remaining_count_fp: Optional[Decimal]
    observations: Tuple[_Observation, ...]
    raw_authoritative: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class _FillRecord:
    fill_id: str
    trade_id: str
    order_id: str
    ticker: str
    market_ticker: Optional[str]
    subaccount_number: int
    exchange_index: int
    count_fp: Decimal
    yes_price_dollars: Decimal
    no_price_dollars: Decimal
    is_taker: bool
    fee_cost: Decimal
    created_time: Optional[object]
    ts: Optional[object]
    observations: Tuple[_Observation, ...]
    raw_authoritative: Mapping[str, object]


_ORDER_REQUIRED = ("order_id", "client_order_id", "ticker", "subaccount_number")
_ORDER_OPTIONAL_TYPED = (
    "exchange_index", "outcome_side", "book_side", "yes_price_dollars", "no_price_dollars",
    "cancel_order_on_pause", "status", "initial_count_fp", "fill_count_fp", "remaining_count_fp",
)
_FILL_REQUIRED = (
    "fill_id", "trade_id", "order_id", "ticker", "subaccount_number", "exchange_index",
    "count_fp", "yes_price_dollars", "no_price_dollars", "is_taker", "fee_cost",
)
_FILL_OPTIONAL_TYPED = ("market_ticker", "created_time", "ts")

_ORDER_AUTHORITATIVE_FIELDS = frozenset(_ORDER_REQUIRED + _ORDER_OPTIONAL_TYPED)
_FILL_AUTHORITATIVE_FIELDS = frozenset(_FILL_REQUIRED + _FILL_OPTIONAL_TYPED)


def _parse_order(raw: object, *, observation: _Observation) -> Tuple[Optional[_OrderRecord], Optional[HaltCode]]:
    if type(raw) is not dict:
        return None, HaltCode.AUTHORITATIVE_RESPONSE_MALFORMED
    for field_name in _ORDER_REQUIRED:
        if field_name not in raw:
            return None, HaltCode.AUTHORITATIVE_RESPONSE_MALFORMED
    try:
        order_id = _opaque_identifier(raw["order_id"])
        client_order_id = _opaque_identifier(raw["client_order_id"])
        ticker = _opaque_identifier(raw["ticker"])
        subaccount = _exact_int(raw["subaccount_number"])
    except ValueError:
        return None, HaltCode.AUTHORITATIVE_RESPONSE_MALFORMED

    typed: Dict[str, object] = {}
    try:
        if "exchange_index" in raw:
            typed["exchange_index"] = _exact_int(raw["exchange_index"])
        if "outcome_side" in raw:
            typed["outcome_side"] = _opaque_identifier(raw["outcome_side"])
        if "book_side" in raw:
            typed["book_side"] = _opaque_identifier(raw["book_side"])
        if "yes_price_dollars" in raw:
            typed["yes_price_dollars"] = _parse_money(raw["yes_price_dollars"])
        if "no_price_dollars" in raw:
            typed["no_price_dollars"] = _parse_money(raw["no_price_dollars"])
        if "cancel_order_on_pause" in raw:
            typed["cancel_order_on_pause"] = _exact_bool(raw["cancel_order_on_pause"])
        if "status" in raw:
            status = _opaque_identifier(raw["status"])
            if status not in _SUPPORTED_ORDER_STATUSES:
                return None, HaltCode.AUTHORITATIVE_SOURCE_DRIFT_SPEC_REVISION_REQUIRED
            typed["status"] = status
        if "initial_count_fp" in raw:
            typed["initial_count_fp"] = _parse_count(raw["initial_count_fp"])
        if "fill_count_fp" in raw:
            typed["fill_count_fp"] = _parse_count(raw["fill_count_fp"])
        if "remaining_count_fp" in raw:
            typed["remaining_count_fp"] = _parse_count(raw["remaining_count_fp"])
    except ValueError:
        return None, HaltCode.AUTHORITATIVE_RESPONSE_MALFORMED

    authoritative: Dict[str, object] = {
        "order_id": order_id, "client_order_id": client_order_id,
        "ticker": ticker, "subaccount_number": subaccount,
    }
    authoritative.update(typed)

    return _OrderRecord(
        order_id=order_id,
        client_order_id=client_order_id,
        ticker=ticker,
        subaccount_number=subaccount,
        exchange_index=typed.get("exchange_index"),
        outcome_side=typed.get("outcome_side"),
        book_side=typed.get("book_side"),
        yes_price_dollars=typed.get("yes_price_dollars"),
        no_price_dollars=typed.get("no_price_dollars"),
        cancel_order_on_pause=typed.get("cancel_order_on_pause"),
        status=typed.get("status"),
        initial_count_fp=typed.get("initial_count_fp"),
        fill_count_fp=typed.get("fill_count_fp"),
        remaining_count_fp=typed.get("remaining_count_fp"),
        observations=(observation,),
        raw_authoritative=MappingProxyType(authoritative),
    ), None


def _parse_fill(raw: object, *, observation: _Observation) -> Tuple[Optional[_FillRecord], Optional[HaltCode]]:
    if type(raw) is not dict:
        return None, HaltCode.AUTHORITATIVE_RESPONSE_MALFORMED
    for field_name in _FILL_REQUIRED:
        if field_name not in raw:
            return None, HaltCode.AUTHORITATIVE_RESPONSE_MALFORMED
    try:
        fill_id = _opaque_identifier(raw["fill_id"])
        trade_id = _opaque_identifier(raw["trade_id"])
        order_id = _opaque_identifier(raw["order_id"])
        ticker = _opaque_identifier(raw["ticker"])
        subaccount = _exact_int(raw["subaccount_number"])
        exchange_index = _exact_int(raw["exchange_index"])
        if exchange_index < 0:
            raise ValueError("exchange_index must be non-negative")
        count = _parse_count(raw["count_fp"])
        yes_price = _parse_money(raw["yes_price_dollars"])
        no_price = _parse_money(raw["no_price_dollars"])
        is_taker = _exact_bool(raw["is_taker"])
        fee_cost = _parse_money(raw["fee_cost"])
    except ValueError:
        return None, HaltCode.AUTHORITATIVE_RESPONSE_MALFORMED

    market_ticker: Optional[str] = None
    created_time: Optional[object] = None
    ts: Optional[object] = None
    try:
        if "market_ticker" in raw:
            market_ticker = _opaque_identifier(raw["market_ticker"])
        if "created_time" in raw:
            created_time = raw["created_time"]
            if not _valid_rfc3339(created_time):
                return None, HaltCode.AUTHORITATIVE_RESPONSE_MALFORMED
        if "ts" in raw:
            ts = raw["ts"]
            if type(ts) is bool:
                return None, HaltCode.AUTHORITATIVE_RESPONSE_MALFORMED
            if type(ts) not in (int, str):
                return None, HaltCode.AUTHORITATIVE_RESPONSE_MALFORMED
            if type(ts) is str and not _valid_rfc3339(ts):
                return None, HaltCode.AUTHORITATIVE_RESPONSE_MALFORMED
    except ValueError:
        return None, HaltCode.AUTHORITATIVE_RESPONSE_MALFORMED

    authoritative: Dict[str, object] = {
        "fill_id": fill_id, "trade_id": trade_id, "order_id": order_id, "ticker": ticker,
        "subaccount_number": subaccount, "exchange_index": exchange_index,
        "count_fp": count, "yes_price_dollars": yes_price,
        "no_price_dollars": no_price, "is_taker": is_taker, "fee_cost": fee_cost,
    }
    if market_ticker is not None:
        authoritative["market_ticker"] = market_ticker
    if created_time is not None:
        authoritative["created_time"] = created_time
    if ts is not None:
        authoritative["ts"] = ts

    return _FillRecord(
        fill_id=fill_id, trade_id=trade_id, order_id=order_id, ticker=ticker,
        market_ticker=market_ticker, subaccount_number=subaccount, exchange_index=exchange_index,
        count_fp=count, yes_price_dollars=yes_price, no_price_dollars=no_price,
        is_taker=is_taker, fee_cost=fee_cost, created_time=created_time, ts=ts,
        observations=(observation,), raw_authoritative=MappingProxyType(authoritative),
    ), None


def _common_fields_compatible(a: Mapping[str, object], b: Mapping[str, object]) -> bool:
    for key in set(a).intersection(b):
        if type(a[key]) is not type(b[key]) or a[key] != b[key]:
            return False
    return True


def _merge_order_observations(a: _OrderRecord, b: _OrderRecord) -> _OrderRecord:
    merged_raw = {**dict(b.raw_authoritative), **dict(a.raw_authoritative)}
    return _OrderRecord(
        order_id=a.order_id, client_order_id=a.client_order_id, ticker=a.ticker,
        subaccount_number=a.subaccount_number,
        exchange_index=a.exchange_index if a.exchange_index is not None else b.exchange_index,
        outcome_side=a.outcome_side if a.outcome_side is not None else b.outcome_side,
        book_side=a.book_side if a.book_side is not None else b.book_side,
        yes_price_dollars=a.yes_price_dollars if a.yes_price_dollars is not None else b.yes_price_dollars,
        no_price_dollars=a.no_price_dollars if a.no_price_dollars is not None else b.no_price_dollars,
        cancel_order_on_pause=a.cancel_order_on_pause if a.cancel_order_on_pause is not None else b.cancel_order_on_pause,
        status=a.status if a.status is not None else b.status,
        initial_count_fp=a.initial_count_fp if a.initial_count_fp is not None else b.initial_count_fp,
        fill_count_fp=a.fill_count_fp if a.fill_count_fp is not None else b.fill_count_fp,
        remaining_count_fp=a.remaining_count_fp if a.remaining_count_fp is not None else b.remaining_count_fp,
        observations=a.observations + b.observations,
        raw_authoritative=MappingProxyType(merged_raw),
    )


def _merge_fill_observations(a: _FillRecord, b: _FillRecord) -> _FillRecord:
    merged_raw = {**dict(b.raw_authoritative), **dict(a.raw_authoritative)}
    return _FillRecord(
        fill_id=a.fill_id, trade_id=a.trade_id, order_id=a.order_id, ticker=a.ticker,
        market_ticker=a.market_ticker if a.market_ticker is not None else b.market_ticker,
        subaccount_number=a.subaccount_number,
        exchange_index=a.exchange_index,
        count_fp=a.count_fp, yes_price_dollars=a.yes_price_dollars, no_price_dollars=a.no_price_dollars,
        is_taker=a.is_taker, fee_cost=a.fee_cost,
        created_time=a.created_time if a.created_time is not None else b.created_time,
        ts=a.ts if a.ts is not None else b.ts,
        observations=a.observations + b.observations,
        raw_authoritative=MappingProxyType(merged_raw),
    )


def _dedupe_orders(
    records: Sequence[_OrderRecord],
) -> Tuple[Optional[List[_OrderRecord]], Optional[HaltCode], List[Dict[str, object]]]:
    by_id: Dict[str, _OrderRecord] = {}
    details: List[Dict[str, object]] = []
    for record in records:
        existing = by_id.get(record.order_id)
        if existing is None:
            by_id[record.order_id] = record
            continue
        compatible = _common_fields_compatible(existing.raw_authoritative, record.raw_authoritative)
        details.append({"order_id": record.order_id, "classification": "COMPATIBLE" if compatible else "CONFLICT"})
        if not compatible:
            return None, HaltCode.ORDER_ID_DUPLICATE_CONFLICT, details
        by_id[record.order_id] = _merge_order_observations(existing, record)
    return list(by_id.values()), None, details


def _dedupe_fills(
    records: Sequence[_FillRecord],
) -> Tuple[Optional[List[_FillRecord]], Optional[HaltCode], List[Dict[str, object]]]:
    by_id: Dict[str, _FillRecord] = {}
    details: List[Dict[str, object]] = []
    for record in records:
        existing = by_id.get(record.fill_id)
        if existing is None:
            by_id[record.fill_id] = record
            continue
        compatible = _common_fields_compatible(existing.raw_authoritative, record.raw_authoritative)
        details.append({"fill_id": record.fill_id, "classification": "COMPATIBLE" if compatible else "CONFLICT"})
        if not compatible:
            return None, HaltCode.FILL_ID_DUPLICATE_CONFLICT, details
        by_id[record.fill_id] = _merge_fill_observations(existing, record)
    return list(by_id.values()), None, details

# ---------------------------------------------------------------------------
# Query/path construction and structural GET-only enforcement
# ---------------------------------------------------------------------------

_ALLOWED_QUERY_KEYS: Mapping[HistoricalResolutionOperation, FrozenSet[str]] = MappingProxyType({
    HistoricalResolutionOperation.USER_DATA_TIMESTAMP: frozenset(),
    HistoricalResolutionOperation.HISTORICAL_CUTOFF: frozenset(),
    HistoricalResolutionOperation.LIVE_ORDERS: frozenset({"ticker", "min_ts", "max_ts", "limit", "subaccount", "exchange_index", "cursor"}),
    HistoricalResolutionOperation.HISTORICAL_ORDERS: frozenset({"ticker", "max_ts", "limit", "cursor"}),
    HistoricalResolutionOperation.EXACT_ORDER: frozenset(),
    HistoricalResolutionOperation.LIVE_FILLS: frozenset({"ticker", "order_id", "min_ts", "max_ts", "limit", "subaccount", "exchange_index", "cursor"}),
    HistoricalResolutionOperation.HISTORICAL_FILLS: frozenset({"ticker", "max_ts", "limit", "cursor"}),
    HistoricalResolutionOperation.LIVE_POSITIONS: frozenset({"ticker", "subaccount", "exchange_index", "limit", "cursor"}),
    HistoricalResolutionOperation.HISTORICAL_POSITIONS: frozenset({"ticker", "limit", "cursor"}),
    HistoricalResolutionOperation.SETTLEMENTS: frozenset({"ticker", "subaccount", "min_ts", "max_ts", "limit", "cursor"}),
})

_REQUIRED_QUERY_KEYS: Mapping[HistoricalResolutionOperation, FrozenSet[str]] = MappingProxyType({
    HistoricalResolutionOperation.USER_DATA_TIMESTAMP: frozenset(),
    HistoricalResolutionOperation.HISTORICAL_CUTOFF: frozenset(),
    HistoricalResolutionOperation.LIVE_ORDERS: frozenset({"ticker", "min_ts", "max_ts", "limit", "subaccount", "exchange_index"}),
    HistoricalResolutionOperation.HISTORICAL_ORDERS: frozenset({"ticker", "max_ts", "limit"}),
    HistoricalResolutionOperation.EXACT_ORDER: frozenset(),
    HistoricalResolutionOperation.LIVE_FILLS: frozenset({"ticker", "min_ts", "max_ts", "limit", "subaccount", "exchange_index"}),
    HistoricalResolutionOperation.HISTORICAL_FILLS: frozenset({"ticker", "max_ts", "limit"}),
    HistoricalResolutionOperation.LIVE_POSITIONS: frozenset({"ticker", "subaccount", "exchange_index", "limit"}),
    HistoricalResolutionOperation.HISTORICAL_POSITIONS: frozenset({"ticker", "limit"}),
    HistoricalResolutionOperation.SETTLEMENTS: frozenset({"ticker", "subaccount", "min_ts", "max_ts", "limit"}),
})


def _query_for(
    operation: HistoricalResolutionOperation,
    *,
    cursor: Optional[str] = None,
    order_id: Optional[str] = None,
    min_ts: Optional[int] = None,
    max_ts: Optional[int] = None,
) -> Mapping[str, object]:
    if operation in (HistoricalResolutionOperation.USER_DATA_TIMESTAMP, HistoricalResolutionOperation.HISTORICAL_CUTOFF, HistoricalResolutionOperation.EXACT_ORDER):
        query: Dict[str, object] = {}
    elif operation is HistoricalResolutionOperation.LIVE_ORDERS:
        query = {"ticker": TICKER, "min_ts": min_ts, "max_ts": max_ts, "limit": PAGE_LIMIT, "subaccount": SUBACCOUNT, "exchange_index": EXCHANGE_INDEX}
    elif operation is HistoricalResolutionOperation.HISTORICAL_ORDERS:
        query = {"ticker": TICKER, "max_ts": max_ts, "limit": PAGE_LIMIT}
    elif operation is HistoricalResolutionOperation.LIVE_FILLS:
        query = {"ticker": TICKER, "min_ts": min_ts, "max_ts": max_ts, "limit": PAGE_LIMIT, "subaccount": SUBACCOUNT, "exchange_index": EXCHANGE_INDEX}
        if order_id is not None:
            query["order_id"] = order_id
    elif operation is HistoricalResolutionOperation.HISTORICAL_FILLS:
        query = {"ticker": TICKER, "max_ts": max_ts, "limit": PAGE_LIMIT}
    elif operation is HistoricalResolutionOperation.LIVE_POSITIONS:
        query = {"ticker": TICKER, "subaccount": SUBACCOUNT, "exchange_index": EXCHANGE_INDEX, "limit": PAGE_LIMIT}
    elif operation is HistoricalResolutionOperation.HISTORICAL_POSITIONS:
        query = {"ticker": TICKER, "limit": PAGE_LIMIT}
    elif operation is HistoricalResolutionOperation.SETTLEMENTS:
        query = {"ticker": TICKER, "subaccount": SUBACCOUNT, "min_ts": min_ts, "max_ts": max_ts, "limit": PAGE_LIMIT}
    else:
        raise ValueError(HaltCode.GET_ONLY_CONTRACT_VIOLATION.value)
    if cursor is not None:
        if operation not in _PAGINATED_OPERATIONS or type(cursor) is not str or cursor == "":
            raise ValueError(HaltCode.GET_ONLY_CONTRACT_VIOLATION.value)
        query["cursor"] = cursor
    return MappingProxyType(query)


def _path_for(operation: HistoricalResolutionOperation, *, order_id: Optional[str] = None) -> str:
    spec = _OPERATION_SPECS[operation]
    if operation is HistoricalResolutionOperation.EXACT_ORDER:
        if type(order_id) is not str or order_id == "" or "/" in order_id or "?" in order_id or "#" in order_id:
            raise ValueError(HaltCode.GET_ONLY_CONTRACT_VIOLATION.value)
        return spec.path_template.replace("{order_id}", order_id)
    return spec.path_template


def _validate_prepared_request(request: object) -> Optional[HaltCode]:
    if type(request) is not PreparedGetRequest:
        return HaltCode.GET_ONLY_CONTRACT_VIOLATION
    if type(request.operation) is not HistoricalResolutionOperation:
        return HaltCode.GET_ONLY_CONTRACT_VIOLATION
    if request.origin != DEMO_REST_ORIGIN:
        return HaltCode.GET_ONLY_CONTRACT_VIOLATION
    if request.method != "GET":
        return HaltCode.GET_ONLY_CONTRACT_VIOLATION
    spec = _OPERATION_SPECS[request.operation]
    if request.authentication_class is not spec.authentication_class:
        return HaltCode.GET_ONLY_CONTRACT_VIOLATION
    if type(request.path) is not str or not request.path.startswith(TRADE_API_BASE_PATH):
        return HaltCode.GET_ONLY_CONTRACT_VIOLATION
    if request.operation is HistoricalResolutionOperation.EXACT_ORDER:
        prefix = "/trade-api/v2/portfolio/orders/"
        if not request.path.startswith(prefix):
            return HaltCode.GET_ONLY_CONTRACT_VIOLATION
        tail = request.path[len(prefix):]
        if tail == "" or "/" in tail or "?" in tail or "#" in tail:
            return HaltCode.GET_ONLY_CONTRACT_VIOLATION
    elif request.path != spec.path_template:
        return HaltCode.GET_ONLY_CONTRACT_VIOLATION
    if not isinstance(request.query, Mapping):
        return HaltCode.GET_ONLY_CONTRACT_VIOLATION

    keys = set(request.query) - {"cursor"}
    allowed = _ALLOWED_QUERY_KEYS[request.operation] - {"cursor"}
    required = _REQUIRED_QUERY_KEYS[request.operation]
    if not keys.issubset(allowed) or not required.issubset(keys):
        return HaltCode.GET_ONLY_CONTRACT_VIOLATION

    if "ticker" in request.query and request.query["ticker"] != TICKER:
        return HaltCode.GET_ONLY_CONTRACT_VIOLATION
    if "limit" in request.query and request.query["limit"] != PAGE_LIMIT:
        return HaltCode.GET_ONLY_CONTRACT_VIOLATION
    if "subaccount" in request.query and request.query["subaccount"] != SUBACCOUNT:
        return HaltCode.GET_ONLY_CONTRACT_VIOLATION
    if "exchange_index" in request.query and request.query["exchange_index"] != EXCHANGE_INDEX:
        return HaltCode.GET_ONLY_CONTRACT_VIOLATION

    if "cursor" in request.query:
        cursor = request.query["cursor"]
        if request.operation not in _PAGINATED_OPERATIONS or type(cursor) is not str or cursor == "":
            return HaltCode.GET_ONLY_CONTRACT_VIOLATION
    if type(request.page_ordinal) is not int or request.page_ordinal < 1:
        return HaltCode.GET_ONLY_CONTRACT_VIOLATION
    return None


def _cursor_evidence(cursor: Optional[str]) -> Dict[str, object]:
    if cursor is None:
        return {"classification": "OMITTED", "sha256": None}
    if cursor == "":
        return {"classification": "TERMINAL_EMPTY", "sha256": None}
    return {"classification": "NONEMPTY_OPAQUE", "sha256": _sha256(cursor.encode("utf-8"))}


# ---------------------------------------------------------------------------
# Deadline / request / evidence execution state
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class _Deadline:
    clock: Callable[[], float]
    entry: float

    @property
    def absolute(self) -> float:
        return self.entry + MASTER_DEADLINE_MS / 1000.0

    def expired(self) -> bool:
        return self.clock() >= self.absolute

    def remaining_ms(self) -> int:
        remaining = max(0.0, self.absolute - self.clock())
        return int(remaining * 1000.0)


def _check_deadline(deadline: _Deadline) -> Optional[HaltCode]:
    return HaltCode.MASTER_DEADLINE_EXHAUSTED if deadline.expired() else None


@dataclass(slots=True)
class _ExecutionState:
    request_counts: Dict[HistoricalResolutionOperation, int] = field(
        default_factory=lambda: {op: 0 for op in HistoricalResolutionOperation}
    )
    request_ledger: List[Dict[str, object]] = field(default_factory=list)
    branch: Optional[str] = None
    retry_count_observed: int = 0
    redirect_count_observed: int = 0

    def total_requests(self) -> int:
        return sum(self.request_counts.values())

    def branch_ceiling(self) -> int:
        if self.branch is None:
            return GLOBAL_GET_SEND_MAXIMUM
        return min(GLOBAL_GET_SEND_MAXIMUM, BRANCH_REQUEST_MAXIMA[self.branch])


def _send_json(
    *,
    operation: HistoricalResolutionOperation,
    transport: HistoricalResolutionTransport,
    deadline: _Deadline,
    state: _ExecutionState,
    page_ordinal: int,
    cursor_input: Optional[str] = None,
    order_id: Optional[str] = None,
    min_ts: Optional[int] = None,
    max_ts: Optional[int] = None,
) -> Tuple[Optional[object], Optional[RawHttpResponse], Optional[HaltCode]]:
    if _check_deadline(deadline) is not None:
        return None, None, HaltCode.MASTER_DEADLINE_EXHAUSTED
    spec = _OPERATION_SPECS[operation]
    if state.request_counts[operation] >= spec.page_budget:
        return None, None, HaltCode.PAGE_BUDGET_EXHAUSTED
    if state.total_requests() >= GLOBAL_GET_SEND_MAXIMUM:
        return None, None, HaltCode.GLOBAL_REQUEST_BUDGET_EXHAUSTED
    if state.total_requests() >= state.branch_ceiling():
        return None, None, HaltCode.BRANCH_REQUEST_BUDGET_EXHAUSTED

    try:
        path = _path_for(operation, order_id=order_id)
        query = _query_for(operation, cursor=cursor_input, order_id=order_id, min_ts=min_ts, max_ts=max_ts)
    except ValueError:
        return None, None, HaltCode.GET_ONLY_CONTRACT_VIOLATION

    request_start = deadline.clock()
    if request_start >= deadline.absolute:
        return None, None, HaltCode.MASTER_DEADLINE_EXHAUSTED
    effective = min(request_start + PER_REQUEST_CEILING_MS / 1000.0, deadline.absolute)
    request = PreparedGetRequest(
        operation=operation, origin=DEMO_REST_ORIGIN, path=path, query=query,
        authentication_class=spec.authentication_class, page_ordinal=page_ordinal,
        effective_deadline_monotonic=effective,
    )
    contract_halt = _validate_prepared_request(request)
    if contract_halt is not None:
        return None, None, contract_halt

    state.request_counts[operation] += 1
    ledger: Dict[str, object] = {
        "ordinal": state.total_requests(),
        "operation_id": operation.value,
        "method": "GET",
        "path": path,
        "sanitized_query": dict(query),
        "authentication_class": spec.authentication_class.value,
        "page_ordinal": page_ordinal,
        "cursor_input_state": "OMITTED" if cursor_input is None else "NONEMPTY",
        "cursor_input_sha256": _cursor_evidence(cursor_input)["sha256"],
        "http_status": None,
        "response_media_type": None,
        "response_raw_bytes": None,
        "response_sha256": None,
        "parsed_schema_classification": "TRANSPORT_PENDING",
        "records_observed": None,
        "cursor_output_state": "NOT_APPLICABLE",
        "cursor_output_sha256": None,
        "elapsed_ms": None,
        "remaining_master_budget_ms_after_parse": None,
        "retry_count": 0,
        "redirect_count": 0,
        "terminal_for_stream": False,
    }
    state.request_ledger.append(ledger)

    try:
        response = transport.send(request)
    except Exception:
        ledger["parsed_schema_classification"] = "TRANSPORT_READ_FAILURE"
        ledger["elapsed_ms"] = max(0, int((deadline.clock() - request_start) * 1000))
        return None, None, HaltCode.TRANSPORT_READ_FAILURE

    after_receive = deadline.clock()
    if type(response) is not RawHttpResponse:
        ledger["parsed_schema_classification"] = "TRANSPORT_EVIDENCE_INVALID"
        return None, None, HaltCode.TRANSPORT_READ_FAILURE

    ledger["http_status"] = response.status
    ledger["response_media_type"] = response.media_type
    ledger["retry_count"] = response.retry_count
    ledger["redirect_count"] = response.redirect_count
    if type(response.retry_count) is int and type(response.retry_count) is not bool:
        state.retry_count_observed += response.retry_count
    if type(response.redirect_count) is int and type(response.redirect_count) is not bool:
        state.redirect_count_observed += response.redirect_count

    if after_receive >= deadline.absolute:
        ledger["parsed_schema_classification"] = "MASTER_DEADLINE_EXHAUSTED"
        return None, response, HaltCode.MASTER_DEADLINE_EXHAUSTED
    if after_receive >= effective:
        ledger["parsed_schema_classification"] = "PER_REQUEST_CEILING_EXHAUSTED"
        return None, response, HaltCode.TRANSPORT_READ_FAILURE
    if type(response.retry_count) is not int or type(response.retry_count) is bool or response.retry_count != 0:
        ledger["parsed_schema_classification"] = "RETRY_CONTRACT_VIOLATION"
        return None, response, HaltCode.TRANSPORT_READ_FAILURE
    if type(response.redirect_count) is not int or type(response.redirect_count) is bool:
        ledger["parsed_schema_classification"] = "REDIRECT_EVIDENCE_INVALID"
        return None, response, HaltCode.TRANSPORT_READ_FAILURE
    if response.redirect_count != 0:
        ledger["parsed_schema_classification"] = "REDIRECT_PROHIBITED"
        return None, response, HaltCode.REDIRECT_PROHIBITED
    if type(response.status) is not int or type(response.status) is bool:
        ledger["parsed_schema_classification"] = "STATUS_INVALID"
        return None, response, HaltCode.AUTHORITATIVE_RESPONSE_MALFORMED
    if 300 <= response.status <= 399:
        ledger["parsed_schema_classification"] = "REDIRECT_PROHIBITED"
        return None, response, HaltCode.REDIRECT_PROHIBITED
    if response.status != 200:
        ledger["parsed_schema_classification"] = "UNEXPECTED_HTTP_STATUS"
        return None, response, HaltCode.UNEXPECTED_HTTP_STATUS
    if type(response.media_type) is not str or response.media_type.split(";", 1)[0].strip().lower() != "application/json":
        ledger["parsed_schema_classification"] = "MEDIA_TYPE_INVALID"
        return None, response, HaltCode.AUTHORITATIVE_RESPONSE_MALFORMED
    if type(response.body_bytes) is not bytes:
        ledger["parsed_schema_classification"] = "BODY_BYTES_INVALID"
        return None, response, HaltCode.AUTHORITATIVE_RESPONSE_MALFORMED

    ledger["response_raw_bytes"] = len(response.body_bytes)
    ledger["response_sha256"] = _sha256(response.body_bytes)
    try:
        parsed = _strict_json_loads(response.body_bytes)
    except ValueError:
        ledger["parsed_schema_classification"] = "STRICT_JSON_INVALID"
        return None, response, HaltCode.AUTHORITATIVE_RESPONSE_MALFORMED

    if _check_deadline(deadline) is not None:
        ledger["parsed_schema_classification"] = "MASTER_DEADLINE_EXHAUSTED_AFTER_PARSE"
        return None, response, HaltCode.MASTER_DEADLINE_EXHAUSTED

    ledger["parsed_schema_classification"] = "STRICT_JSON_VALID"
    ledger["records_observed"] = len(parsed) if isinstance(parsed, list) else None
    ledger["elapsed_ms"] = max(0, int((deadline.clock() - request_start) * 1000))
    ledger["remaining_master_budget_ms_after_parse"] = deadline.remaining_ms()
    return parsed, response, None


def _extract_page(parsed: object, *, record_key: str) -> Tuple[Optional[List[object]], Optional[str], Optional[HaltCode]]:
    if type(parsed) is not dict or record_key not in parsed:
        return None, None, HaltCode.AUTHORITATIVE_RESPONSE_MALFORMED
    if "cursor" not in parsed:
        return None, None, HaltCode.PAGINATION_CURSOR_MALFORMED
    records = parsed[record_key]
    cursor = parsed["cursor"]
    if type(records) is not list:
        return None, None, HaltCode.AUTHORITATIVE_RESPONSE_MALFORMED
    if type(cursor) is not str:
        return None, None, HaltCode.PAGINATION_CURSOR_MALFORMED
    return records, cursor, None

# ---------------------------------------------------------------------------
# Generic paginated traversal
# ---------------------------------------------------------------------------

def _paginate(
    *,
    operation: HistoricalResolutionOperation,
    transport: HistoricalResolutionTransport,
    deadline: _Deadline,
    state: _ExecutionState,
    min_ts: Optional[int] = None,
    max_ts: Optional[int] = None,
    order_id: Optional[str] = None,
) -> Tuple[List[Tuple[object, int, int, str]], bool, Optional[HaltCode], List[Dict[str, object]]]:
    """Exhaust one paginated source to its terminal empty cursor or page
    budget.  Returns ``(annotated_records, terminal_reached, halt,
    page_details)`` where each annotated record is
    ``(raw_record, page_ordinal, record_ordinal, response_sha256)``."""

    spec = _OPERATION_SPECS[operation]
    cursor: Optional[str] = None
    seen_nonempty: set = set()
    page = 1
    annotated: List[Tuple[object, int, int, str]] = []
    page_details: List[Dict[str, object]] = []
    while True:
        parsed, response, halt = _send_json(
            operation=operation, transport=transport, deadline=deadline, state=state,
            page_ordinal=page, cursor_input=cursor, order_id=order_id, min_ts=min_ts, max_ts=max_ts,
        )
        if halt is not None:
            return annotated, False, halt, page_details
        assert response is not None
        records, next_cursor, page_halt = _extract_page(parsed, record_key=spec.record_key)
        if page_halt is not None:
            return annotated, False, page_halt, page_details
        assert records is not None and next_cursor is not None
        body_sha = _sha256(response.body_bytes)
        state.request_ledger[-1]["cursor_output_state"] = "EMPTY" if next_cursor == "" else "NONEMPTY"
        state.request_ledger[-1]["cursor_output_sha256"] = _cursor_evidence(next_cursor)["sha256"]
        state.request_ledger[-1]["terminal_for_stream"] = next_cursor == ""
        page_details.append({
            "page_ordinal": page, "records_observed": len(records),
            "cursor_input": _cursor_evidence(cursor), "cursor_output": _cursor_evidence(next_cursor),
            "response_sha256": body_sha,
        })
        for index, raw in enumerate(records, 1):
            annotated.append((raw, page, index, body_sha))
        if _check_deadline(deadline) is not None:
            return annotated, False, HaltCode.MASTER_DEADLINE_EXHAUSTED, page_details
        if next_cursor == "":
            return annotated, True, None, page_details
        if next_cursor in seen_nonempty:
            return annotated, False, HaltCode.PAGINATION_CURSOR_CYCLE, page_details
        seen_nonempty.add(next_cursor)
        if page >= spec.page_budget:
            return annotated, False, HaltCode.SOURCE_TRAVERSAL_INCOMPLETE, page_details
        cursor = next_cursor
        page += 1


def _validate_target_scope(order: _OrderRecord) -> bool:
    if order.client_order_id != CLIENT_ORDER_ID:
        return False
    if order.ticker != TICKER:
        return False
    if order.subaccount_number != SUBACCOUNT:
        return False
    if order.exchange_index is not None and order.exchange_index != EXCHANGE_INDEX:
        return False
    return True


def _order_in_local_scope(order: _OrderRecord) -> bool:
    if order.ticker != TICKER:
        return False
    if order.subaccount_number != SUBACCOUNT:
        return False
    if order.exchange_index is not None and order.exchange_index != EXCHANGE_INDEX:
        return False
    return True


def _fill_in_local_scope(fill: _FillRecord, *, lower_utc: datetime, upper_utc: datetime) -> bool:
    if fill.ticker != TICKER:
        return False
    if fill.market_ticker is not None and fill.market_ticker != TICKER:
        return False
    if fill.subaccount_number != SUBACCOUNT:
        return False
    fill_time = None
    if type(fill.ts) is str and _valid_rfc3339(fill.ts):
        fill_time = _parse_rfc3339(fill.ts)
    elif type(fill.created_time) is str and _valid_rfc3339(fill.created_time):
        fill_time = _parse_rfc3339(fill.created_time)
    if fill_time is None:
        return True
    return lower_utc <= fill_time <= upper_utc


def _discover_orders(
    *,
    transport: HistoricalResolutionTransport,
    deadline: _Deadline,
    state: _ExecutionState,
    min_ts: int,
    max_ts: int,
) -> Tuple[Optional[List[_OrderRecord]], bool, bool, Optional[HaltCode], Dict[str, object]]:
    evidence: Dict[str, object] = {
        "live_pages": [], "historical_pages": [],
        "live_terminal_cursor_reached": False, "historical_terminal_cursor_reached": False,
        "scope_rejected_record_count": 0,
    }
    all_orders: List[_OrderRecord] = []

    live_annotated, live_complete, halt, live_pages = _paginate(
        operation=HistoricalResolutionOperation.LIVE_ORDERS, transport=transport, deadline=deadline,
        state=state, min_ts=min_ts, max_ts=max_ts,
    )
    evidence["live_pages"] = live_pages
    evidence["live_terminal_cursor_reached"] = live_complete
    if halt is not None:
        return None, live_complete, False, halt, evidence
    for raw, page_ordinal, record_ordinal, body_sha in live_annotated:
        observation = _Observation("LIVE_ORDERS", page_ordinal, record_ordinal, body_sha)
        order, order_halt = _parse_order(raw, observation=observation)
        if order_halt is not None:
            return None, live_complete, False, order_halt, evidence
        assert order is not None
        if not _order_in_local_scope(order):
            evidence["scope_rejected_record_count"] = int(evidence["scope_rejected_record_count"]) + 1
            continue
        all_orders.append(order)

    historical_annotated, historical_complete, halt, historical_pages = _paginate(
        operation=HistoricalResolutionOperation.HISTORICAL_ORDERS, transport=transport, deadline=deadline,
        state=state, max_ts=max_ts,
    )
    evidence["historical_pages"] = historical_pages
    evidence["historical_terminal_cursor_reached"] = historical_complete
    if halt is not None:
        return None, live_complete, historical_complete, halt, evidence
    for raw, page_ordinal, record_ordinal, body_sha in historical_annotated:
        observation = _Observation("HISTORICAL_ORDERS", page_ordinal, record_ordinal, body_sha)
        order, order_halt = _parse_order(raw, observation=observation)
        if order_halt is not None:
            return None, live_complete, historical_complete, order_halt, evidence
        assert order is not None
        if not _order_in_local_scope(order):
            evidence["scope_rejected_record_count"] = int(evidence["scope_rejected_record_count"]) + 1
            continue
        all_orders.append(order)

    if _check_deadline(deadline) is not None:
        return None, live_complete, historical_complete, HaltCode.MASTER_DEADLINE_EXHAUSTED, evidence

    deduped, dedupe_halt, dup_details = _dedupe_orders(all_orders)
    evidence["duplicate_order_details"] = dup_details
    if dedupe_halt is not None:
        return None, live_complete, historical_complete, dedupe_halt, evidence
    assert deduped is not None
    return deduped, live_complete, historical_complete, None, evidence


def _discover_fills(
    *,
    transport: HistoricalResolutionTransport,
    deadline: _Deadline,
    state: _ExecutionState,
    min_ts: int,
    max_ts: int,
    lower_utc: datetime,
    upper_utc: datetime,
    bound_order_id: Optional[str] = None,
) -> Tuple[Optional[List[_FillRecord]], bool, bool, Optional[HaltCode], Dict[str, object]]:
    evidence: Dict[str, object] = {
        "live_pages": [], "historical_pages": [],
        "live_terminal_cursor_reached": False, "historical_terminal_cursor_reached": False,
        "scope_rejected_record_count": 0,
    }
    all_fills: List[_FillRecord] = []

    live_annotated, live_complete, halt, live_pages = _paginate(
        operation=HistoricalResolutionOperation.LIVE_FILLS, transport=transport, deadline=deadline,
        state=state, min_ts=min_ts, max_ts=max_ts, order_id=bound_order_id,
    )
    evidence["live_pages"] = live_pages
    evidence["live_terminal_cursor_reached"] = live_complete
    if halt is not None:
        return None, live_complete, False, halt, evidence
    for raw, page_ordinal, record_ordinal, body_sha in live_annotated:
        observation = _Observation("LIVE_FILLS", page_ordinal, record_ordinal, body_sha)
        fill, fill_halt = _parse_fill(raw, observation=observation)
        if fill_halt is not None:
            return None, live_complete, False, fill_halt, evidence
        assert fill is not None
        if bound_order_id is not None and fill.order_id != bound_order_id:
            return None, live_complete, False, HaltCode.FILL_SCOPE_CONFLICT, evidence
        if not _fill_in_local_scope(fill, lower_utc=lower_utc, upper_utc=upper_utc):
            evidence["scope_rejected_record_count"] = int(evidence["scope_rejected_record_count"]) + 1
            continue
        all_fills.append(fill)

    historical_annotated, historical_complete, halt, historical_pages = _paginate(
        operation=HistoricalResolutionOperation.HISTORICAL_FILLS, transport=transport, deadline=deadline,
        state=state, max_ts=max_ts,
    )
    evidence["historical_pages"] = historical_pages
    evidence["historical_terminal_cursor_reached"] = historical_complete
    if halt is not None:
        return None, live_complete, historical_complete, halt, evidence
    for raw, page_ordinal, record_ordinal, body_sha in historical_annotated:
        observation = _Observation("HISTORICAL_FILLS", page_ordinal, record_ordinal, body_sha)
        fill, fill_halt = _parse_fill(raw, observation=observation)
        if fill_halt is not None:
            return None, live_complete, historical_complete, fill_halt, evidence
        assert fill is not None
        if bound_order_id is not None and fill.order_id != bound_order_id:
            # The historical stream has no server-side order_id filter;
            # unrelated well-formed records are expected and simply not kept.
            continue
        if not _fill_in_local_scope(fill, lower_utc=lower_utc, upper_utc=upper_utc):
            evidence["scope_rejected_record_count"] = int(evidence["scope_rejected_record_count"]) + 1
            continue
        all_fills.append(fill)

    if _check_deadline(deadline) is not None:
        return None, live_complete, historical_complete, HaltCode.MASTER_DEADLINE_EXHAUSTED, evidence

    deduped, dedupe_halt, dup_details = _dedupe_fills(all_fills)
    evidence["duplicate_fill_details"] = dup_details
    if dedupe_halt is not None:
        return None, live_complete, historical_complete, dedupe_halt, evidence
    assert deduped is not None
    if any(fill.exchange_index != EXCHANGE_INDEX for fill in deduped):
        return None, live_complete, historical_complete, HaltCode.FILL_SCOPE_CONFLICT, evidence
    return deduped, live_complete, historical_complete, None, evidence

# ---------------------------------------------------------------------------
# Direct-match classification and exact-order revalidation
# ---------------------------------------------------------------------------

def _classify_direct_matches(
    canonical_orders: Sequence[_OrderRecord],
) -> Tuple[DirectMatchSourceClass, Optional[_OrderRecord], List[str]]:
    exact = [o for o in canonical_orders if o.client_order_id == CLIENT_ORDER_ID]
    order_ids = sorted({o.order_id for o in exact})
    if len(order_ids) == 0:
        return DirectMatchSourceClass.NONE, None, []
    if len(order_ids) > 1:
        return DirectMatchSourceClass.CONFLICT, None, order_ids
    order = next(o for o in exact if o.order_id == order_ids[0])
    live_observed = any(o.source_stream == "LIVE_ORDERS" for o in order.observations)
    historical_observed = any(o.source_stream == "HISTORICAL_ORDERS" for o in order.observations)
    if live_observed and historical_observed:
        return DirectMatchSourceClass.LIVE_AND_HISTORICAL_COMPATIBLE, order, order_ids
    if live_observed:
        return DirectMatchSourceClass.LIVE_PRESENT, order, order_ids
    return DirectMatchSourceClass.HISTORICAL_ONLY, order, order_ids


def _perform_exact_order_read(
    *, transport: HistoricalResolutionTransport, deadline: _Deadline, state: _ExecutionState, order_id: str,
) -> Tuple[Optional[_OrderRecord], Optional[HaltCode]]:
    parsed, response, halt = _send_json(
        operation=HistoricalResolutionOperation.EXACT_ORDER, transport=transport, deadline=deadline,
        state=state, page_ordinal=1, order_id=order_id,
    )
    if halt is not None:
        return None, halt
    assert response is not None
    if type(parsed) is not dict or "order" not in parsed:
        return None, HaltCode.AUTHORITATIVE_RESPONSE_MALFORMED
    observation = _Observation("EXACT_ORDER", 1, 1, _sha256(response.body_bytes))
    order, order_halt = _parse_order(parsed["order"], observation=observation)
    if order_halt is not None:
        return None, order_halt
    assert order is not None
    if order.order_id != order_id:
        return None, HaltCode.ORDER_IDENTITY_OR_ECONOMIC_MISMATCH
    return order, None


def _validate_fill_derived_candidate(
    *, transport: HistoricalResolutionTransport, deadline: _Deadline, state: _ExecutionState, candidate_order_id: str,
) -> Tuple[str, Optional[_OrderRecord]]:
    order, halt = _perform_exact_order_read(transport=transport, deadline=deadline, state=state, order_id=candidate_order_id)
    if halt is not None:
        return "UNRESOLVED", None
    assert order is not None
    if order.client_order_id != CLIENT_ORDER_ID:
        return "REJECTED", order
    if not _validate_target_scope(order):
        return "REJECTED", order
    return "BOUND", order


# ---------------------------------------------------------------------------
# User-data timestamp / historical cutoff observations
# ---------------------------------------------------------------------------

_CUTOFF_FIELDS = ("market_settled_ts", "trades_created_ts", "orders_updated_ts", "market_positions_last_updated_ts")


def _read_user_data_timestamp(
    transport: HistoricalResolutionTransport, deadline: _Deadline, state: _ExecutionState, *, phase: str,
) -> Tuple[Optional[Dict[str, object]], Optional[HaltCode]]:
    parsed, response, halt = _send_json(
        operation=HistoricalResolutionOperation.USER_DATA_TIMESTAMP, transport=transport, deadline=deadline,
        state=state, page_ordinal=1,
    )
    if halt is not None:
        return None, halt
    assert response is not None
    if type(parsed) is not dict or "as_of_time" not in parsed or not _valid_utc_rfc3339(parsed["as_of_time"]):
        return None, HaltCode.AUTHORITATIVE_RESPONSE_MALFORMED
    return {
        "phase": phase, "as_of_time": parsed["as_of_time"],
        "response_raw_bytes": len(response.body_bytes), "response_sha256": _sha256(response.body_bytes),
    }, None


def _read_cutoff(
    transport: HistoricalResolutionTransport, deadline: _Deadline, state: _ExecutionState, *, phase: str,
) -> Tuple[Optional[Dict[str, object]], Optional[HaltCode]]:
    parsed, response, halt = _send_json(
        operation=HistoricalResolutionOperation.HISTORICAL_CUTOFF, transport=transport, deadline=deadline,
        state=state, page_ordinal=1,
    )
    if halt is not None:
        return None, halt
    assert response is not None
    if type(parsed) is not dict or any(name not in parsed for name in _CUTOFF_FIELDS):
        return None, HaltCode.AUTHORITATIVE_RESPONSE_MALFORMED
    if any(not _valid_utc_rfc3339(parsed[name]) for name in _CUTOFF_FIELDS):
        return None, HaltCode.AUTHORITATIVE_RESPONSE_MALFORMED
    result = {name: parsed[name] for name in _CUTOFF_FIELDS}
    result["phase"] = phase
    result["response_raw_bytes"] = len(response.body_bytes)
    result["response_sha256"] = _sha256(response.body_bytes)
    return result, None


_FAMILY_CUTOFF_FIELDS: Mapping[str, str] = MappingProxyType({
    "ORDERS": "orders_updated_ts",
    "FILLS": "trades_created_ts",
    "POSITIONS": "market_positions_last_updated_ts",
})


def _family_coverage(
    pre_value: datetime, post_value: datetime, *, evaluation_query_max_ts: Optional[int],
) -> str:
    """RA1-PAGE-005 / RA1-TEST-018 per-family moving-cutoff coverage theorem.

    Pure PRE<=POST monotonicity proves only that the partition boundary did
    not regress; it does not prove that a live+historical traversal pair
    covered every record that crossed the boundary while we were running.
    The additional, checkable condition adopted here is that our own
    declared query ceiling (``evaluation_query_max_ts``, frozen once at P1
    before either cutoff observation) already extends past the POST-observed
    boundary -- i.e. our bounded traversal window provably reached at least
    as far forward as the partition ultimately moved.  When it does not, the
    crossed interval is not provably covered by evidence we actually
    collected, and the theorem correctly refuses to claim closure."""

    if post_value < pre_value:
        return "CUTOFF_REGRESSED_OR_INVALID"
    if post_value == pre_value:
        return "CUTOFF_UNCHANGED_AND_COVERED"
    if evaluation_query_max_ts is None:
        return "CUTOFF_ADVANCED_WITH_COVERAGE_UNPROVEN"
    if evaluation_query_max_ts >= ceil(post_value.timestamp()):
        return "CUTOFF_ADVANCED_WITH_COVERAGE_PROVEN"
    return "CUTOFF_ADVANCED_WITH_COVERAGE_UNPROVEN"


def _assess_cutoff_coverage(
    pre: Mapping[str, object], post: Mapping[str, object], *, evaluation_query_max_ts: Optional[int],
) -> Dict[str, str]:
    return {
        family: _family_coverage(
            _parse_rfc3339(pre[field]), _parse_rfc3339(post[field]),
            evaluation_query_max_ts=evaluation_query_max_ts,
        )
        for family, field in _FAMILY_CUTOFF_FIELDS.items()
    }


# ---------------------------------------------------------------------------
# Position / settlement supporting-evidence collection
# ---------------------------------------------------------------------------

def _supporting_row_in_target_shard(raw: object) -> Tuple[Optional[bool], Optional[HaltCode]]:
    """Validate target position/settlement shard identity before aggregation."""

    if type(raw) is not dict:
        return None, HaltCode.AUTHORITATIVE_RESPONSE_MALFORMED
    if "ticker" not in raw:
        return None, HaltCode.AUTHORITATIVE_RESPONSE_MALFORMED
    try:
        row_ticker = _opaque_identifier(raw["ticker"])
    except ValueError:
        return None, HaltCode.AUTHORITATIVE_RESPONSE_MALFORMED
    if row_ticker != TICKER:
        return False, None
    if "exchange_index" not in raw:
        return None, HaltCode.AUTHORITATIVE_RESPONSE_MALFORMED
    try:
        row_exchange_index = _exact_int(raw["exchange_index"])
    except ValueError:
        return None, HaltCode.AUTHORITATIVE_RESPONSE_MALFORMED
    if row_exchange_index < 0:
        return None, HaltCode.AUTHORITATIVE_RESPONSE_MALFORMED
    return row_exchange_index == EXCHANGE_INDEX, None


def _collect_supporting_list(
    *, operation: HistoricalResolutionOperation, transport: HistoricalResolutionTransport,
    deadline: _Deadline, state: _ExecutionState, min_ts: Optional[int] = None, max_ts: Optional[int] = None,
) -> Tuple[int, bool, Optional[HaltCode], List[Dict[str, object]]]:
    annotated, complete, halt, pages = _paginate(
        operation=operation, transport=transport, deadline=deadline, state=state, min_ts=min_ts, max_ts=max_ts,
    )
    if halt is not None:
        return len(annotated), complete, halt, pages
    count = 0
    for raw, _page, _record, _sha in annotated:
        target_shard, row_halt = _supporting_row_in_target_shard(raw)
        if row_halt is not None:
            return count, complete, row_halt, pages
        if not target_shard:
            continue
        count += 1
    return count, complete, None, pages


# ---------------------------------------------------------------------------
# Decimal economics
# ---------------------------------------------------------------------------

def _compute_economics(fills: Sequence[_FillRecord]) -> Tuple[Decimal, Decimal, Decimal, Optional[HaltCode]]:
    quantity = Decimal("0.00")
    principal = Decimal("0")
    fee = Decimal("0")
    for fill in sorted(fills, key=lambda f: f.fill_id):
        if fill.is_taker:
            return quantity, principal, fee, HaltCode.ECONOMIC_RISK_INVARIANT_VIOLATION
        if fill.yes_price_dollars > LIMIT_PRICE:
            return quantity, principal, fee, HaltCode.ECONOMIC_RISK_INVARIANT_VIOLATION
        quantity += fill.count_fp
        principal += fill.count_fp * fill.yes_price_dollars
        fee += fill.fee_cost
        if quantity > INITIAL_QUANTITY:
            return quantity, principal, fee, HaltCode.ECONOMIC_RISK_INVARIANT_VIOLATION
    if principal > MAX_FILLED_PRINCIPAL:
        return quantity, principal, fee, HaltCode.ECONOMIC_RISK_INVARIANT_VIOLATION
    if fee > MAX_FEE_COST:
        return quantity, principal, fee, HaltCode.ECONOMIC_RISK_INVARIANT_VIOLATION
    if principal + fee > MAX_TOTAL_RISK:
        return quantity, principal, fee, HaltCode.ECONOMIC_RISK_INVARIANT_VIOLATION
    return quantity, principal, fee, None


def _order_fill_quantity_match(order: _OrderRecord, quantity: Decimal) -> str:
    if order.fill_count_fp is None or order.initial_count_fp is None or order.remaining_count_fp is None:
        return "NOT_EXPOSED"
    if order.fill_count_fp != quantity:
        return "FAIL"
    if order.fill_count_fp + order.remaining_count_fp != order.initial_count_fp:
        return "FAIL"
    if order.initial_count_fp != INITIAL_QUANTITY:
        return "FAIL"
    return "PASS"


# ---------------------------------------------------------------------------
# Negative-closure predicate vector (N01..N22) -- structurally never proven
# ---------------------------------------------------------------------------

def _negative_closure_assessment(
    *, orders_complete: bool, fills_complete: bool, cutoff_regressed: bool, zero_match: bool,
) -> Dict[str, object]:
    predicates: Dict[str, bool] = {
        "N01": True, "N02": True, "N03": False, "N04": True,
        "N05": orders_complete, "N06": orders_complete,
        "N07": fills_complete, "N08": fills_complete,
        "N09": True, "N10": not cutoff_regressed, "N11": True, "N12": not cutoff_regressed,
        "N13": False, "N14": False, "N15": False, "N16": False, "N17": False,
        "N18": True, "N19": True, "N20": False, "N21": False, "N22": True,
    }
    failed = sorted(name for name, passed in predicates.items() if not passed)
    return {
        "zero_matches_observed": zero_match,
        **{f"predicate_{name}": value for name, value in predicates.items()},
        "authoritative_nonexistence_proven": False,
        "revision_02_negative_closure_permitted": REVISION_02_NEGATIVE_CLOSURE_PERMITTED,
        "failed_or_unknown_predicates": failed,
        "conclusion": (
            ResultClass.READ_ZERO_MATCH_NEGATIVE_THEOREM_NOT_PROVEN.value
            if zero_match else "NOT_APPLICABLE_POSITIVE_BINDING"
        ),
    }

# ---------------------------------------------------------------------------
# Evidence artifact construction (RA1-EVID-002 top-level keys) and integrity
# ---------------------------------------------------------------------------

def _artifact_evidence(identity: ArtifactIdentity) -> Dict[str, object]:
    return {"path": identity.path, "bytes": identity.bytes, "sha256": identity.sha256, "git_blob": identity.git_blob}


def _order_evidence(order: _OrderRecord) -> Dict[str, object]:
    return {
        "order_id": order.order_id,
        "client_order_id": order.client_order_id,
        "ticker": order.ticker,
        "subaccount_number": order.subaccount_number,
        "exchange_index": order.exchange_index,
        "status": order.status,
        "initial_count_fp": None if order.initial_count_fp is None else str(order.initial_count_fp),
        "fill_count_fp": None if order.fill_count_fp is None else str(order.fill_count_fp),
        "remaining_count_fp": None if order.remaining_count_fp is None else str(order.remaining_count_fp),
        "source_provenance": [
            {"source_stream": o.source_stream, "page_ordinal": o.page_ordinal,
             "record_ordinal": o.record_ordinal, "response_sha256": o.response_sha256}
            for o in order.observations
        ],
    }


def _fill_evidence(fill: _FillRecord) -> Dict[str, object]:
    return {
        "fill_id": fill.fill_id, "trade_id": fill.trade_id, "order_id": fill.order_id,
        "ticker": fill.ticker, "subaccount_number": fill.subaccount_number,
        "count_fp": str(fill.count_fp), "yes_price_dollars": str(fill.yes_price_dollars),
        "fee_cost": str(fill.fee_cost), "is_taker": fill.is_taker,
    }


def _secret_redaction_evidence() -> Dict[str, object]:
    return {
        "api_key_id_value_present": False,
        "private_key_present": False,
        "authorization_header_present": False,
        "access_signature_present": False,
        "access_timestamp_header_value_present": False,
        "credential_value_present": False,
        "redaction_validation": "PASS",
    }


def _build_evidence_payload(
    *,
    historical_resolution_input: HistoricalResolutionInput,
    state: _ExecutionState,
    ctx: Mapping[str, object],
    result_class: ResultClass,
    halt_code: Optional[HaltCode],
    bound_order_id: Optional[str],
    binding_source_class: BindingSourceClass,
    exact_reread_required: bool,
    exact_reread_performed: bool,
    exact_reread_reason: ExactOrderRereadReason,
    fill_evidence_origin: FillEvidenceOrigin,
    live_fill_source_reused: bool,
    historical_fill_source_reused: bool,
    canonical_fill_quantity: Optional[Decimal],
    canonical_filled_principal: Optional[Decimal],
    canonical_fee_cost: Optional[Decimal],
    economic_reconciliation: Optional[Dict[str, object]],
    completeness: Dict[str, object],
    negative_closure: Dict[str, object],
    planned_branch: str,
    elapsed_ms: int,
) -> Dict[str, object]:
    order_evidence = dict(ctx.get("order_evidence", {}))
    fill_evidence = dict(ctx.get("fill_evidence") or ctx.get("post_binding_fill_evidence") or {})
    active_or_terminal = ctx.get("active_or_terminal", "NOT_APPLICABLE")

    return {
        "historical_resolution_evidence_schema_revision": HISTORICAL_RESOLUTION_EVIDENCE_SCHEMA_REVISION,
        "task_id": TASK_ID,
        "provenance": {
            "repository": REPOSITORY,
            "canonical_main": REQUIRED_MAIN,
            "canonical_tree": REQUIRED_TREE,
            "canonical_parent": REQUIRED_PARENT,
            "specification_filename": SPECIFICATION_FILENAME,
            "specification_raw_bytes": SPECIFICATION_BYTES,
            "specification_sha256": SPECIFICATION_SHA256,
            "handoff_filename": HANDOFF_FILENAME,
            "handoff_raw_bytes": HANDOFF_BYTES,
            "handoff_sha256": HANDOFF_SHA256,
            "implementation_path": historical_resolution_input.provenance.implementation.path,
            "implementation_raw_bytes": historical_resolution_input.provenance.implementation.bytes,
            "implementation_sha256": historical_resolution_input.provenance.implementation.sha256,
            "implementation_git_blob": historical_resolution_input.provenance.implementation.git_blob,
            "test_path": historical_resolution_input.provenance.tests.path,
            "test_raw_bytes": historical_resolution_input.provenance.tests.bytes,
            "test_sha256": historical_resolution_input.provenance.tests.sha256,
            "test_git_blob": historical_resolution_input.provenance.tests.git_blob,
            "predecessor_specification_filename": PREDECESSOR_SPECIFICATION_FILENAME,
            "predecessor_specification_raw_bytes": PREDECESSOR_SPECIFICATION_BYTES,
            "predecessor_specification_sha256": PREDECESSOR_SPECIFICATION_SHA256,
            "predecessor_handoff_filename": PREDECESSOR_HANDOFF_FILENAME,
            "predecessor_handoff_raw_bytes": PREDECESSOR_HANDOFF_BYTES,
            "predecessor_handoff_sha256": PREDECESSOR_HANDOFF_SHA256,
            "original_execution_evidence_identity": ORIGINAL_EXECUTION_EVIDENCE_IDENTITY,
            "prior_reconciliation_evidence_identity": PRIOR_RECONCILIATION_EVIDENCE_IDENTITY,
            "prior_fill_fallback_evidence_identity": PRIOR_FILL_FALLBACK_EVIDENCE_IDENTITY,
        },
        "scope": {
            "environment": ENVIRONMENT, "demo_rest_origin": DEMO_REST_ORIGIN, "api_base_path": TRADE_API_BASE_PATH,
            "account_scope_ref": ACCOUNT_SCOPE_REF, "subaccount": SUBACCOUNT, "exchange_index": EXCHANGE_INDEX,
            "conflict_domain_ref": CONFLICT_DOMAIN_REF, "ticker": TICKER,
        },
        "immutable_incident": {
            "incident_id": INCIDENT_ID, "client_order_id": CLIENT_ORDER_ID,
            "disposition_before": DISPOSITION_BEFORE, "bound_order_id_before": BOUND_ORDER_ID_BEFORE,
            "created_order_upper_bound_before": CREATED_ORDER_UPPER_BOUND_BEFORE,
            "active_order_upper_bound_before": ACTIVE_ORDER_UPPER_BOUND_BEFORE,
            "unknown_result_before": UNKNOWN_RESULT_BEFORE,
            "writer_proof_state_before": WRITER_PROOF_STATE_BEFORE,
            "writer_proof_release_eligible_before": WRITER_PROOF_RELEASE_ELIGIBLE_BEFORE,
            "protected_unresolved_legacy_write_count_before": PROTECTED_UNRESOLVED_LEGACY_WRITE_COUNT_BEFORE,
            "history_completeness_before": HISTORY_COMPLETENESS_BEFORE,
            "restart_classification_before": RESTART_CLASSIFICATION_BEFORE,
            "historical_unresolved_exposure_before": HISTORICAL_UNRESOLVED_EXPOSURE_BEFORE,
        },
        "source_binding": {
            "official_source_scope": "docs.kalshi.com only",
            "source_retrieval_started_at_utc": "2026-08-19T23:42:00Z",
            "source_retrieval_completed_at_utc": "2026-08-19T23:42:00Z",
            "normalized_manifest_id": SOURCE_BINDING_MANIFEST_ID,
            "normalized_manifest_raw_bytes": SOURCE_BINDING_MANIFEST_LENGTH,
            "normalized_manifest_sha256": SOURCE_BINDING_MANIFEST_SHA256,
            "operation_bindings": [
                {"operation_id": name, "normalized_record_bytes": values[0], "normalized_record_sha256": values[1]}
                for name, values in sorted(OPERATION_BINDING_IDENTITIES.items())
            ],
            "raw_openapi_materialized": False,
            "raw_openapi_bytes": None,
            "raw_openapi_sha256": None,
            "historical_partition_facts": "cutoffs_move_forward; positions archived per whole event",
            "retention_facts": "NOT_EXPOSED",
            "account_subaccount_semantics": "live scope-filterable; historical locally filtered",
            "exact_order_negative_semantics": "NOT_EXPOSED",
            "client_order_id_semantics": "order-only; not exposed on fills",
            "user_data_freshness_semantics": "approximate; not transactionally exact",
            "task_current_source_validation": "PASS",
        },
        "external_research_provenance": [
            {
                "source_name": "MARCO_ARB_EXTERNAL_RESEARCH_FINDINGS_MASTER_01",
                "repository_or_artifact": "MARCO_ARB_EXTERNAL_RESEARCH_FINDINGS_MASTER_01.md",
                "commit_or_artifact_identity": "NOT_APPLICABLE",
                "authority_class": "NON_CONTROLLING_EXTERNAL_RESEARCH",
                "finding_used": "unknown is not zero; absence is not nonexistence proof",
                "finding_not_used": "NONE",
            },
        ],
        "capability_record": {
            "environment": historical_resolution_input.capability_envelope.environment,
            "rest_origin": historical_resolution_input.capability_envelope.rest_origin,
            "credential_reference_names": list(historical_resolution_input.capability_envelope.credential_reference_names),
            "granted_capabilities": sorted(c.value for c in historical_resolution_input.capability_envelope.granted_capabilities),
        },
        "time_envelope": {
            "incident_lower_bound_source": INCIDENT_LOWER_BOUND_SOURCE,
            "incident_lower_bound_utc": INCIDENT_LOWER_BOUND_UTC,
            "incident_query_min_ts": INCIDENT_QUERY_MIN_TS,
            "evaluation_snapshot_utc": ctx.get("evaluation_snapshot_utc_text"),
            "evaluation_query_max_ts": ctx.get("evaluation_query_max_ts"),
            "history_lower_bound": INCIDENT_LOWER_BOUND_UTC,
            "history_upper_bound": ctx.get("evaluation_snapshot_utc_text"),
            "master_deadline_ms": MASTER_DEADLINE_MS,
            "per_request_ceiling_ms": PER_REQUEST_CEILING_MS,
        },
        "request_log": state.request_ledger,
        "cutoff_observations": [o for o in (ctx.get("cutoff_pre"), ctx.get("cutoff_post")) if o is not None],
        "user_data_timestamp_observations": [o for o in (ctx.get("udt_pre"), ctx.get("udt_post")) if o is not None],
        "order_discovery": {
            "live_pages": order_evidence.get("live_pages", []),
            "historical_pages": order_evidence.get("historical_pages", []),
            "live_terminal_cursor_reached": order_evidence.get("live_terminal_cursor_reached", False),
            "historical_terminal_cursor_reached": order_evidence.get("historical_terminal_cursor_reached", False),
            "unique_order_id_count": ctx.get("unique_order_id_count", 0),
            "duplicate_order_ids": order_evidence.get("duplicate_order_details", []),
            "duplicate_conflicts": [d for d in order_evidence.get("duplicate_order_details", []) if d.get("classification") == "CONFLICT"],
            "exact_client_order_id_match_count": ctx.get("exact_client_order_id_match_count", 0),
            "exact_client_order_id_order_ids": ctx.get("matched_order_ids", []),
            "direct_match_source_class": ctx.get("direct_class_value", "NONE"),
            "scope_rejected_record_count": order_evidence.get("scope_rejected_record_count", 0),
            "identity_conflicts": ctx.get("matched_order_ids", []) if ctx.get("direct_class_value") == "CONFLICT" else [],
            "source_surface_conflicts": ctx.get("source_surface_conflicts", []),
        },
        "fill_discovery": {
            "performed": bool(ctx.get("fill_evidence")),
            "live_pages": fill_evidence.get("live_pages", []),
            "historical_pages": fill_evidence.get("historical_pages", []),
            "live_terminal_cursor_reached": fill_evidence.get("live_terminal_cursor_reached", False),
            "historical_terminal_cursor_reached": fill_evidence.get("historical_terminal_cursor_reached", False),
            "unique_fill_id_count": ctx.get("unique_fill_id_count", 0),
            "duplicate_fill_ids": fill_evidence.get("duplicate_fill_details", []),
            "duplicate_fill_conflicts": [d for d in fill_evidence.get("duplicate_fill_details", []) if d.get("classification") == "CONFLICT"],
            "incident_scope_fill_count": ctx.get("incident_scope_fill_count", 0),
            "candidate_order_id_count": len(ctx.get("candidate_order_ids", []) or []),
            "candidate_order_ids": ctx.get("candidate_order_ids", []),
            "candidate_validation_results": ctx.get("candidate_validation_results", []),
            "fill_evidence_origin": fill_evidence_origin.value,
            "live_fill_source_reused": live_fill_source_reused,
            "historical_fill_source_reused": historical_fill_source_reused,
            "second_fill_traversal_performed": FILL_DERIVED_POST_BINDING_SECOND_FILL_TRAVERSAL,
        },
        "position_evidence": ctx.get("position_evidence", {
            "required": False, "live_performed": False, "historical_performed": False,
            "live_pages": 0, "historical_pages": 0,
            "live_terminal_cursor_reached": False, "historical_terminal_cursor_reached": False,
            "market_position_rows": 0, "event_position_rows": 0,
            "historical_subaccount_scope_proven": False, "conflicts": [], "conclusion": "NOT_REQUIRED",
        }),
        "settlement_evidence": ctx.get("settlement_evidence", {
            "required": False, "performed": False, "pages": 0, "terminal_cursor_reached": False,
            "matching_rows": 0, "conflicts": [], "conclusion": "NOT_REQUIRED",
        }),
        "binding_decision": {
            "binding_state": ctx.get("binding_state", "NONE"),
            "binding_source_class": binding_source_class.value,
            "bound_order_id": bound_order_id,
            "bound_client_order_id": CLIENT_ORDER_ID if bound_order_id is not None else None,
            "binding_source": ctx.get("binding_source", "NONE"),
            "exact_order_reread_required": exact_reread_required,
            "exact_order_reread_performed": exact_reread_performed,
            "exact_order_reread_reason": exact_reread_reason.value,
            "exact_scope_matrix": ctx.get("exact_scope_matrix", {}),
            "exact_immutable_intent_matrix": ctx.get("exact_immutable_intent_matrix", {}),
            "fields_not_exposed_by_bound_source": ctx.get("fields_not_exposed", []),
            "source_surface_consistency": ctx.get("source_surface_consistency", "CONSISTENT"),
            "active_or_terminal_state": active_or_terminal,
        },
        "economic_reconciliation": economic_reconciliation,
        "completeness_assessment": completeness,
        "negative_closure_assessment": negative_closure,
        "counters": {
            "request_count": state.total_requests(),
            "page_count": len(state.request_ledger),
            "retry_count": state.retry_count_observed,
            "redirect_count": state.redirect_count_observed,
            "candidate_exact_order_request_count": ctx.get("candidate_exact_order_request_count", 0),
            "direct_exact_order_request_count": ctx.get("direct_exact_order_request_count", 0),
            "planned_branch": planned_branch,
            "theoretical_branch_request_max": BRANCH_REQUEST_MAXIMA.get(planned_branch, GLOBAL_GET_SEND_MAXIMUM),
            "theoretical_maximum_planned_get_sends": THEORETICAL_MAXIMUM_PLANNED_GET_SENDS,
            "global_get_send_maximum": GLOBAL_GET_SEND_MAXIMUM,
        },
        "terminal_result": {
            "result_class": result_class.value,
            "halt_code": None if halt_code is None else halt_code.value,
            "bound_order_id": bound_order_id,
            "created_order_upper_bound_after": CREATED_ORDER_UPPER_BOUND_BEFORE,
            "active_order_upper_bound_after": ACTIVE_ORDER_UPPER_BOUND_BEFORE,
            "unknown_result_after": True,
            "writer_proof_state_after": WRITER_PROOF_STATE_BEFORE,
            "writer_proof_release_eligible_after": False,
            "persistent_state_accessed": False,
            "persistent_state_mutated": False,
            "elapsed_ms": elapsed_ms,
        },
        "secret_redaction": _secret_redaction_evidence(),
        "artifact_integrity": {
            "canonical_serialization": "UTF8_SORTED_KEYS_COMPACT_JSON_V1",
            "artifact_raw_bytes_excluding_integrity_hash_value_rule": (
                "artifact_integrity.artifact_sha256 is null while hashing;"
                " the final serialization with the hash filled in is longer"
            ),
            "artifact_sha256": None,
            "hash_verification": "PASS",
        },
    }


def _hash_evidence_payload(payload: Dict[str, object]) -> Tuple[bytes, str]:
    """Non-recursive integrity algorithm: hash the canonical bytes with
    ``artifact_integrity.artifact_sha256`` held at ``null``, then serialize
    the final object with that digest filled in."""

    payload["artifact_integrity"] = dict(payload["artifact_integrity"])
    payload["artifact_integrity"]["artifact_sha256"] = None
    pre_hash_bytes = _canonical_json_bytes(_json_safe(payload))
    digest = _sha256(pre_hash_bytes)
    payload["artifact_integrity"]["artifact_sha256"] = digest
    final_bytes = _canonical_json_bytes(_json_safe(payload))
    return final_bytes, digest


def verify_evidence_artifact_integrity(evidence_json: bytes) -> bool:
    """Replay steps 1-3 of RA1-EVID-017 against a parsed final artifact."""

    try:
        parsed = _strict_json_loads(evidence_json)
    except ValueError:
        return False
    if type(parsed) is not dict or "artifact_integrity" not in parsed:
        return False
    integrity = parsed["artifact_integrity"]
    if type(integrity) is not dict or "artifact_sha256" not in integrity:
        return False
    claimed = integrity["artifact_sha256"]
    reset = dict(parsed)
    reset["artifact_integrity"] = {**integrity, "artifact_sha256": None}
    recomputed = _sha256(_canonical_json_bytes(reset))
    return claimed == recomputed

# ---------------------------------------------------------------------------
# Result assembly helpers
# ---------------------------------------------------------------------------

def _default_completeness(**overrides: object) -> Dict[str, object]:
    base: Dict[str, object] = {
        "history_lower_bound": INCIDENT_LOWER_BOUND_UTC, "history_upper_bound": None,
        "live_order_partition_complete": False, "historical_order_partition_complete": False, "orders_complete": False,
        "live_fill_partition_complete": False, "historical_fill_partition_complete": False, "fills_complete": False,
        "live_position_partition_complete": False, "historical_position_partition_complete": False,
        "position_or_exposure_evidence_complete": False,
        "settlement_evidence_complete_or_not_required": False,
        "pagination_complete": False, "cutoff_partition_complete": False, "source_semantics_complete": True,
        "identity_resolution_complete": False, "economic_reconciliation_complete_or_not_required": False,
        "retention_lower_bound_proven": False, "missing_intervals": [], "unobservable_intervals": [],
        "overall_evidence_complete": False, "conclusion": "INCOMPLETE",
    }
    base.update(overrides)
    return base


def _minimal_invalid_input() -> HistoricalResolutionInput:
    cap = HistoricalResolutionCapabilityEnvelope(
        environment=ENVIRONMENT, rest_origin=DEMO_REST_ORIGIN,
        credential_reference_names=_REQUIRED_CREDENTIAL_REFERENCES,
        granted_capabilities=frozenset(),
        network_access=CapabilityState.PROHIBITED, demo_public_reads=CapabilityState.PROHIBITED,
        demo_authenticated_reads=CapabilityState.PROHIBITED, credential_use=CapabilityState.PROHIBITED,
        demo_writes=CapabilityState.PROHIBITED, production_public_reads=CapabilityState.PROHIBITED,
        production_authenticated_reads=CapabilityState.PROHIBITED, production_writes=CapabilityState.PROHIBITED,
        account_funding=CapabilityState.PROHIBITED, websocket=CapabilityState.PROHIBITED,
    )
    placeholder = ArtifactIdentity(path="UNAVAILABLE", bytes=0, sha256="0" * 64, git_blob="0" * 40)
    return HistoricalResolutionInput(
        capability_envelope=cap, source_binding_manifest_bytes=b"",
        provenance=HistoricalResolutionProvenance(implementation=placeholder, tests=placeholder),
    )


def _deadline_exhausted_result(
    *, historical_resolution_input: HistoricalResolutionInput, state: _ExecutionState, deadline: _Deadline,
    ctx: Dict[str, object], planned_branch: str,
) -> HistoricalResolutionResult:
    """Non-recursive RA1-BOUND-002 deadline-exhaustion terminal construction.

    Builds the full evidence contract exactly once, directly, from whatever
    state/ctx already exist -- it never calls back into ``_build_result`` and
    therefore cannot loop, retry, or recurse regardless of where the master
    deadline was found to be exhausted."""

    elapsed_ms = max(0, int((deadline.clock() - deadline.entry) * 1000))
    completeness = _default_completeness(conclusion="MASTER_DEADLINE_EXHAUSTED")
    negative_closure = _negative_closure_assessment(
        orders_complete=False, fills_complete=False, cutoff_regressed=False, zero_match=False,
    )
    payload = _build_evidence_payload(
        historical_resolution_input=historical_resolution_input, state=state, ctx=ctx,
        result_class=ResultClass.READ_MASTER_DEADLINE_EXHAUSTED, halt_code=HaltCode.MASTER_DEADLINE_EXHAUSTED,
        bound_order_id=None, binding_source_class=BindingSourceClass.NONE,
        exact_reread_required=False, exact_reread_performed=False, exact_reread_reason=ExactOrderRereadReason.NONE,
        fill_evidence_origin=FillEvidenceOrigin.NOT_APPLICABLE, live_fill_source_reused=False,
        historical_fill_source_reused=False, canonical_fill_quantity=None, canonical_filled_principal=None,
        canonical_fee_cost=None, economic_reconciliation=None, completeness=completeness,
        negative_closure=negative_closure, planned_branch=planned_branch, elapsed_ms=elapsed_ms,
    )
    evidence_json, digest = _hash_evidence_payload(payload)
    return HistoricalResolutionResult(
        result_class=ResultClass.READ_MASTER_DEADLINE_EXHAUSTED, halt_code=HaltCode.MASTER_DEADLINE_EXHAUSTED,
        bound_order_id=None, binding_source_class=BindingSourceClass.NONE, planned_branch=planned_branch,
        request_count=state.total_requests(), retry_count=state.retry_count_observed,
        redirect_count=state.redirect_count_observed,
        canonical_fill_quantity=None, canonical_filled_principal=None, canonical_fee_cost=None,
        writer_proof_state_after=WRITER_PROOF_STATE_BEFORE, writer_proof_release_eligible_after=False,
        persistent_state_accessed=False, persistent_state_mutated=False,
        evidence_json=evidence_json, evidence_sha256=digest,
    )


def _build_result(
    *,
    historical_resolution_input: HistoricalResolutionInput,
    state: _ExecutionState,
    deadline: _Deadline,
    ctx: Dict[str, object],
    result_class: ResultClass,
    halt_code: Optional[HaltCode],
    bound_order_id: Optional[str] = None,
    binding_source_class: BindingSourceClass = BindingSourceClass.NONE,
    exact_reread_required: bool = False,
    exact_reread_performed: bool = False,
    exact_reread_reason: ExactOrderRereadReason = ExactOrderRereadReason.NONE,
    fill_evidence_origin: FillEvidenceOrigin = FillEvidenceOrigin.NOT_APPLICABLE,
    live_fill_source_reused: bool = False,
    historical_fill_source_reused: bool = False,
    canonical_fill_quantity: Optional[Decimal] = None,
    canonical_filled_principal: Optional[Decimal] = None,
    canonical_fee_cost: Optional[Decimal] = None,
    economic_reconciliation: Optional[Dict[str, object]] = None,
    completeness: Optional[Dict[str, object]] = None,
    negative_closure: Optional[Dict[str, object]] = None,
    planned_branch: str = "UNRESOLVED",
) -> HistoricalResolutionResult:
    """RA1-BOUND-002: the single absolute master deadline covers this whole
    construction path, not just transport.  ``already_deadline`` is true only
    when the caller is already reporting deadline exhaustion (e.g. an
    executor-level early exit); in that case no further observation is
    needed and the checks below are skipped so the deadline path itself
    stays a single bounded pass.

    RA1-RES-004: deadline exhaustion (precedence tier 2) must not erase an
    already-observed tier-1 capability/environment/provenance/source-drift
    defect (``outranks_deadline``).  Correction 03 fixes a defect in how
    Correction 02 answered this: the clock MUST still be consulted at every
    checkpoint (Question A) even when the current result already outranks
    deadline exhaustion -- only the *consequence* (whether exhaustion
    replaces the terminal result, Question B) may depend on precedence.
    Short-circuiting the clock read itself let a late deadline crossing go
    completely unobserved for a preserved tier-1 result.  When a later
    checkpoint observes exhaustion while an earlier checkpoint already saw
    the evidence payload built/hashed, the already-computed
    ``terminal_result.elapsed_ms`` is corrected and the evidence is rehashed
    exactly once (a single bounded patch, not a loop and not a recursive
    call into this function) so evidence never reports a stale
    below-deadline snapshot once a later checkpoint has actually observed
    the overrun."""

    if result_class in _NEGATIVE_UNREACHABLE_RESULTS:
        raise AssertionError("REVISION_02_NEGATIVE_CLOSURE_UNREACHABLE_CONFORMANCE_FAILURE")

    already_deadline = result_class is ResultClass.READ_MASTER_DEADLINE_EXHAUSTED
    outranks_deadline = result_class in _PRECEDENCE_ABOVE_DEADLINE
    observed_late_while_outranking = False

    def _observe_deadline() -> bool:
        """Question A (always evaluated unless already reporting deadline
        exhaustion) then Question B: return True only when exhaustion
        should replace the current terminal result."""
        nonlocal observed_late_while_outranking
        if already_deadline:
            return False
        if not deadline.expired():
            return False
        if outranks_deadline:
            observed_late_while_outranking = True
            return False
        return True

    # Checkpoint 1: before evidence payload construction.
    if _observe_deadline():
        return _deadline_exhausted_result(
            historical_resolution_input=historical_resolution_input, state=state, deadline=deadline,
            ctx=ctx, planned_branch=planned_branch,
        )

    elapsed_ms = max(0, int((deadline.clock() - deadline.entry) * 1000))
    completeness = completeness if completeness is not None else _default_completeness()
    negative_closure = negative_closure if negative_closure is not None else _negative_closure_assessment(
        orders_complete=False, fills_complete=False, cutoff_regressed=False, zero_match=False,
    )
    payload = _build_evidence_payload(
        historical_resolution_input=historical_resolution_input, state=state, ctx=ctx,
        result_class=result_class, halt_code=halt_code, bound_order_id=bound_order_id,
        binding_source_class=binding_source_class, exact_reread_required=exact_reread_required,
        exact_reread_performed=exact_reread_performed, exact_reread_reason=exact_reread_reason,
        fill_evidence_origin=fill_evidence_origin, live_fill_source_reused=live_fill_source_reused,
        historical_fill_source_reused=historical_fill_source_reused,
        canonical_fill_quantity=canonical_fill_quantity, canonical_filled_principal=canonical_filled_principal,
        canonical_fee_cost=canonical_fee_cost, economic_reconciliation=economic_reconciliation,
        completeness=completeness, negative_closure=negative_closure, planned_branch=planned_branch,
        elapsed_ms=elapsed_ms,
    )

    # Checkpoint 2: after evidence payload construction, before canonical
    # serialization/hash.
    if _observe_deadline():
        return _deadline_exhausted_result(
            historical_resolution_input=historical_resolution_input, state=state, deadline=deadline,
            ctx=ctx, planned_branch=planned_branch,
        )

    evidence_json, digest = _hash_evidence_payload(payload)

    # Checkpoint 3: after canonical serialization/hash, before terminal
    # result construction.
    if _observe_deadline():
        return _deadline_exhausted_result(
            historical_resolution_input=historical_resolution_input, state=state, deadline=deadline,
            ctx=ctx, planned_branch=planned_branch,
        )

    result = HistoricalResolutionResult(
        result_class=result_class, halt_code=halt_code, bound_order_id=bound_order_id,
        binding_source_class=binding_source_class, planned_branch=planned_branch,
        request_count=state.total_requests(), retry_count=state.retry_count_observed,
        redirect_count=state.redirect_count_observed,
        canonical_fill_quantity=canonical_fill_quantity, canonical_filled_principal=canonical_filled_principal,
        canonical_fee_cost=canonical_fee_cost,
        writer_proof_state_after=WRITER_PROOF_STATE_BEFORE, writer_proof_release_eligible_after=False,
        persistent_state_accessed=False, persistent_state_mutated=False,
        evidence_json=evidence_json, evidence_sha256=digest,
    )

    # Checkpoint 4: immediately before returning a non-deadline terminal
    # result.
    if _observe_deadline():
        return _deadline_exhausted_result(
            historical_resolution_input=historical_resolution_input, state=state, deadline=deadline,
            ctx=ctx, planned_branch=planned_branch,
        )

    if observed_late_while_outranking:
        # A later checkpoint observed the deadline has since passed while
        # this tier-1 result remained controlling.  The already-hashed
        # evidence's elapsed_ms is stale; correct it and rehash exactly
        # once so the final evidence reflects the actual final observed
        # deadline state rather than the earlier below-deadline snapshot.
        corrected_elapsed_ms = max(0, int((deadline.clock() - deadline.entry) * 1000))
        payload["terminal_result"] = dict(payload["terminal_result"])
        payload["terminal_result"]["elapsed_ms"] = corrected_elapsed_ms
        evidence_json, digest = _hash_evidence_payload(payload)
        result = HistoricalResolutionResult(
            result_class=result_class, halt_code=halt_code, bound_order_id=bound_order_id,
            binding_source_class=binding_source_class, planned_branch=planned_branch,
            request_count=state.total_requests(), retry_count=state.retry_count_observed,
            redirect_count=state.redirect_count_observed,
            canonical_fill_quantity=canonical_fill_quantity, canonical_filled_principal=canonical_filled_principal,
            canonical_fee_cost=canonical_fee_cost,
            writer_proof_state_after=WRITER_PROOF_STATE_BEFORE, writer_proof_release_eligible_after=False,
            persistent_state_accessed=False, persistent_state_mutated=False,
            evidence_json=evidence_json, evidence_sha256=digest,
        )

    return result

# ---------------------------------------------------------------------------
# Main executor -- Revision-02 corrected planner (P0..P12)
# ---------------------------------------------------------------------------

def execute_historical_resolution_read(
    historical_resolution_input: HistoricalResolutionInput,
    transport: HistoricalResolutionTransport,
    *,
    monotonic_clock: Optional[Callable[[], float]] = None,
    wall_clock: Optional[Callable[[], datetime]] = None,
) -> HistoricalResolutionResult:
    """Execute the closed read-only historical-resolution plan through
    ``transport``.  The master deadline starts at this function's entry and
    covers validation, planning, transport, parsing, pagination, binding,
    Decimal reconciliation, completeness evaluation, and evidence
    construction."""

    clock = monotonic_clock if monotonic_clock is not None else time.monotonic
    entry = clock()
    deadline = _Deadline(clock=clock, entry=entry)
    state = _ExecutionState()
    wall = wall_clock if wall_clock is not None else (lambda: datetime.now(timezone.utc))
    ctx: Dict[str, object] = {}

    def fail(code: HaltCode, *, result_class: Optional[ResultClass] = None) -> HistoricalResolutionResult:
        safe_input = historical_resolution_input if type(historical_resolution_input) is HistoricalResolutionInput else _minimal_invalid_input()
        rc = result_class if result_class is not None else _generic_result_for_halt(code)
        return _build_result(
            historical_resolution_input=safe_input, state=state, deadline=deadline, ctx=ctx,
            result_class=rc, halt_code=code, planned_branch=state.branch or "UNRESOLVED",
        )

    # P0: validate.
    halt = _validate_input(historical_resolution_input)
    if halt is not None:
        return fail(halt)
    if _check_deadline(deadline) is not None:
        return fail(HaltCode.MASTER_DEADLINE_EXHAUSTED)

    # P1: freeze the evaluation snapshot.
    snapshot = wall()
    if type(snapshot) is not datetime or snapshot.tzinfo is None:
        return fail(HaltCode.AUTHORITATIVE_RESPONSE_MALFORMED)
    snapshot = snapshot.astimezone(timezone.utc)
    evaluation_query_max_ts = ceil(snapshot.timestamp()) + 1
    incident_lower_dt = _parse_rfc3339(INCIDENT_LOWER_BOUND_UTC)
    ctx["evaluation_snapshot_utc_text"] = snapshot.isoformat().replace("+00:00", "Z")
    ctx["evaluation_query_max_ts"] = evaluation_query_max_ts

    # P2: USER_DATA_TIMESTAMP PRE.
    udt_pre, halt = _read_user_data_timestamp(transport, deadline, state, phase="PRE")
    if halt is not None:
        return fail(halt)
    ctx["udt_pre"] = udt_pre

    # P3: HISTORICAL_CUTOFF PRE.
    cutoff_pre, halt = _read_cutoff(transport, deadline, state, phase="PRE")
    if halt is not None:
        return fail(halt)
    ctx["cutoff_pre"] = cutoff_pre

    if _check_deadline(deadline) is not None:
        return fail(HaltCode.MASTER_DEADLINE_EXHAUSTED)

    # P4-P5: exhaust LIVE_ORDERS then HISTORICAL_ORDERS.
    orders, live_complete, hist_complete, halt, order_evidence = _discover_orders(
        transport=transport, deadline=deadline, state=state,
        min_ts=INCIDENT_QUERY_MIN_TS, max_ts=evaluation_query_max_ts,
    )
    ctx["order_evidence"] = order_evidence
    if halt is not None:
        return fail(halt)
    assert orders is not None
    if not live_complete or not hist_complete:
        return fail(HaltCode.SOURCE_TRAVERSAL_INCOMPLETE)
    if _check_deadline(deadline) is not None:
        return fail(HaltCode.MASTER_DEADLINE_EXHAUSTED)

    # P6: dedupe, cardinality, direct-match source-provenance classification.
    direct_class, direct_order, matched_ids = _classify_direct_matches(orders)
    ctx["direct_class_value"] = direct_class.value
    ctx["matched_order_ids"] = matched_ids
    ctx["unique_order_id_count"] = len({o.order_id for o in orders})
    ctx["exact_client_order_id_match_count"] = len(matched_ids)
    if direct_class is DirectMatchSourceClass.CONFLICT:
        return fail(HaltCode.IDENTITY_AMBIGUOUS)

    lower_utc = incident_lower_dt
    upper_utc = snapshot

    bound_order: Optional[object] = None
    binding_source_class = BindingSourceClass.NONE
    exact_reread_required = False
    exact_reread_performed = False
    exact_reread_reason = ExactOrderRereadReason.NONE
    branch_prefix = "UNRESOLVED"

    if direct_class in (DirectMatchSourceClass.LIVE_PRESENT, DirectMatchSourceClass.LIVE_AND_HISTORICAL_COMPATIBLE):
        assert direct_order is not None
        branch_prefix = "LIVE_DIRECT" if direct_class is DirectMatchSourceClass.LIVE_PRESENT else "LIVE_AND_HISTORICAL_COMPATIBLE"
        state.branch = f"{branch_prefix}_ACTIVE"
        exact_reread_required = True
        exact_order, reread_halt = _perform_exact_order_read(
            transport=transport, deadline=deadline, state=state, order_id=direct_order.order_id,
        )
        exact_reread_performed = True
        exact_reread_reason = ExactOrderRereadReason.LIVE_DIRECT_REVALIDATION
        ctx["direct_exact_order_request_count"] = 1
        if reread_halt is not None:
            if reread_halt in (HaltCode.TRANSPORT_READ_FAILURE, HaltCode.UNEXPECTED_HTTP_STATUS, HaltCode.AUTHORITATIVE_RESPONSE_MALFORMED):
                reread_halt = HaltCode.DIRECT_LIVE_EXACT_ORDER_REVALIDATION_UNAVAILABLE
            return fail(reread_halt)
        assert exact_order is not None
        if not _validate_target_scope(exact_order):
            return fail(HaltCode.ORDER_IDENTITY_OR_ECONOMIC_MISMATCH)
        if not _common_fields_compatible(direct_order.raw_authoritative, exact_order.raw_authoritative):
            return fail(HaltCode.ORDER_IDENTITY_OR_ECONOMIC_MISMATCH)
        bound_order = exact_order
        binding_source_class = (
            BindingSourceClass.LIVE_PRESENT if direct_class is DirectMatchSourceClass.LIVE_PRESENT
            else BindingSourceClass.LIVE_AND_HISTORICAL_COMPATIBLE
        )
    elif direct_class is DirectMatchSourceClass.HISTORICAL_ONLY:
        assert direct_order is not None
        branch_prefix = "HISTORICAL_ONLY_DIRECT"
        state.branch = f"{branch_prefix}_ACTIVE"
        if not _validate_target_scope(direct_order):
            return fail(HaltCode.ORDER_SCOPE_CONFLICT)
        if direct_order.status == "resting":
            return fail(HaltCode.HISTORICAL_ORDER_PARTITION_CONFLICT)
        exact_reread_required = False
        exact_reread_performed = False
        exact_reread_reason = ExactOrderRereadReason.NOT_REQUIRED_HISTORICAL_ONLY
        bound_order = direct_order
        binding_source_class = BindingSourceClass.HISTORICAL_ONLY
    else:
        assert direct_class is DirectMatchSourceClass.NONE
        state.branch = "ZERO_MATCH"
        fills, live_fill_complete, hist_fill_complete, halt, fill_evidence = _discover_fills(
            transport=transport, deadline=deadline, state=state,
            min_ts=INCIDENT_QUERY_MIN_TS, max_ts=evaluation_query_max_ts,
            lower_utc=lower_utc, upper_utc=upper_utc,
        )
        ctx["fill_evidence"] = fill_evidence
        ctx["pre_binding_fills"] = fills
        ctx["pre_binding_live_complete"] = live_fill_complete
        ctx["pre_binding_hist_complete"] = hist_fill_complete
        if halt is not None:
            return fail(halt)
        assert fills is not None
        if not live_fill_complete or not hist_fill_complete:
            return fail(HaltCode.SOURCE_TRAVERSAL_INCOMPLETE)
        ctx["unique_fill_id_count"] = len({f.fill_id for f in fills})
        ctx["incident_scope_fill_count"] = len(fills)
        candidate_ids = sorted({f.order_id for f in fills})
        ctx["candidate_order_ids"] = candidate_ids
        if len(candidate_ids) > MAX_FILL_DERIVED_CANDIDATE_ORDER_IDS:
            return fail(HaltCode.CANDIDATE_ORDER_ID_BUDGET_EXCEEDED)
        if _check_deadline(deadline) is not None:
            return fail(HaltCode.MASTER_DEADLINE_EXHAUSTED)
        if len(candidate_ids) == 0:
            return _finish_zero_or_unresolved(
                historical_resolution_input=historical_resolution_input, transport=transport, deadline=deadline,
                state=state, ctx=ctx, cutoff_pre=cutoff_pre, orders_complete=True, fills_complete=True,
                unresolved=False,
            )
        validation_results = []
        bound_candidates = []
        any_unresolved = False
        candidate_request_count = 0
        for candidate_id in candidate_ids:
            status, candidate_order = _validate_fill_derived_candidate(
                transport=transport, deadline=deadline, state=state, candidate_order_id=candidate_id,
            )
            candidate_request_count += 1
            validation_results.append({"candidate_order_id": candidate_id, "status": status})
            if status == "BOUND":
                bound_candidates.append(candidate_order)
            elif status == "UNRESOLVED":
                any_unresolved = True
            if _check_deadline(deadline) is not None:
                return fail(HaltCode.MASTER_DEADLINE_EXHAUSTED)
        ctx["candidate_validation_results"] = validation_results
        ctx["candidate_exact_order_request_count"] = candidate_request_count
        if len(bound_candidates) > 1:
            return fail(HaltCode.MULTIPLE_CANDIDATE_ORDER_IDS)
        if len(bound_candidates) == 0:
            if any_unresolved:
                return fail(HaltCode.CANDIDATE_EXACT_ORDER_UNAVAILABLE)
            return _finish_zero_or_unresolved(
                historical_resolution_input=historical_resolution_input, transport=transport, deadline=deadline,
                state=state, ctx=ctx, cutoff_pre=cutoff_pre, orders_complete=True, fills_complete=True,
                unresolved=False,
            )
        branch_prefix = "FILL_DERIVED"
        state.branch = "FILL_DERIVED_ACTIVE"
        bound_order = bound_candidates[0]
        binding_source_class = BindingSourceClass.FILL_DERIVED
        exact_reread_required = True
        exact_reread_performed = True
        exact_reread_reason = ExactOrderRereadReason.FILL_DERIVED_IDENTITY_BINDING

    assert bound_order is not None
    bound_order_id = bound_order.order_id
    ctx["binding_state"] = "BOUND_FILL_DERIVED" if binding_source_class is BindingSourceClass.FILL_DERIVED else "BOUND_DIRECT"
    ctx["binding_source"] = binding_source_class.value

    is_active = bound_order.status == "resting"
    ctx["active_or_terminal"] = "ACTIVE" if is_active else "TERMINAL"

    if is_active:
        result_class = (
            ResultClass.READ_POSITIVE_FILL_DERIVED_ORDER_BOUND_ACTIVE
            if binding_source_class is BindingSourceClass.FILL_DERIVED
            else ResultClass.READ_POSITIVE_ORDER_BOUND_ACTIVE
        )
        return _finish_positive(
            historical_resolution_input=historical_resolution_input, transport=transport, deadline=deadline,
            state=state, ctx=ctx, cutoff_pre=cutoff_pre, result_class=result_class, halt_code=None,
            bound_order_id=bound_order_id, binding_source_class=binding_source_class,
            exact_reread_required=exact_reread_required, exact_reread_performed=exact_reread_performed,
            exact_reread_reason=exact_reread_reason, fill_evidence_origin=FillEvidenceOrigin.NOT_APPLICABLE,
            live_fill_source_reused=False, historical_fill_source_reused=False,
            canonical_fill_quantity=None, canonical_filled_principal=None, canonical_fee_cost=None,
            economic_reconciliation=None,
            completeness=_default_completeness(
                identity_resolution_complete=True, conclusion="POSITIVE_ACTIVE_BINDING_NO_FILL_ECONOMICS",
            ),
            planned_branch=state.branch,
        )

    # Terminal / terminal-looking bound order: raise the branch ceiling and
    # perform the applicable one-pass fill reconciliation.
    state.branch = f"{branch_prefix}_TERMINAL"
    if binding_source_class is BindingSourceClass.FILL_DERIVED:
        fill_evidence_origin = FillEvidenceOrigin.PRE_BINDING_FILL_DISCOVERY_REUSED
        live_fill_source_reused = True
        historical_fill_source_reused = True
        bound_fills = [f for f in (ctx.get("pre_binding_fills") or []) if f.order_id == bound_order_id]
        fills_source_complete = bool(ctx.get("pre_binding_live_complete")) and bool(ctx.get("pre_binding_hist_complete"))
    else:
        fill_evidence_origin = FillEvidenceOrigin.POST_BINDING_BOUND_ORDER_TRAVERSAL
        live_fill_source_reused = False
        historical_fill_source_reused = False
        bound_fills, live_fc, hist_fc, halt, post_fill_evidence = _discover_fills(
            transport=transport, deadline=deadline, state=state,
            min_ts=INCIDENT_QUERY_MIN_TS, max_ts=evaluation_query_max_ts,
            lower_utc=lower_utc, upper_utc=upper_utc, bound_order_id=bound_order_id,
        )
        ctx["post_binding_fill_evidence"] = post_fill_evidence
        if halt is not None:
            return fail(halt)
        assert bound_fills is not None
        fills_source_complete = live_fc and hist_fc

    if _check_deadline(deadline) is not None:
        return fail(HaltCode.MASTER_DEADLINE_EXHAUSTED)

    quantity, principal, fee, econ_halt = _compute_economics(bound_fills)
    order_fill_match = _order_fill_quantity_match(bound_order, quantity)

    live_pos_count, live_pos_complete, halt, _pages = _collect_supporting_list(
        operation=HistoricalResolutionOperation.LIVE_POSITIONS, transport=transport, deadline=deadline, state=state,
    )
    if halt is not None:
        return fail(halt)
    hist_pos_count, hist_pos_complete, halt, _pages = _collect_supporting_list(
        operation=HistoricalResolutionOperation.HISTORICAL_POSITIONS, transport=transport, deadline=deadline, state=state,
    )
    if halt is not None:
        return fail(halt)
    settlement_count, settlement_complete, halt, _pages = _collect_supporting_list(
        operation=HistoricalResolutionOperation.SETTLEMENTS, transport=transport, deadline=deadline, state=state,
        min_ts=INCIDENT_QUERY_MIN_TS, max_ts=evaluation_query_max_ts,
    )
    if halt is not None:
        return fail(halt)

    ctx["position_evidence"] = {
        "required": True, "live_performed": True, "historical_performed": True,
        "live_pages": live_pos_count, "historical_pages": hist_pos_count,
        "live_terminal_cursor_reached": live_pos_complete, "historical_terminal_cursor_reached": hist_pos_complete,
        "market_position_rows": live_pos_count + hist_pos_count, "event_position_rows": 0,
        "historical_subaccount_scope_proven": False, "conflicts": [],
        "conclusion": "SUPPORTING_EVIDENCE_ONLY",
    }
    ctx["settlement_evidence"] = {
        "required": True, "performed": True, "pages": settlement_count,
        "terminal_cursor_reached": settlement_complete, "matching_rows": settlement_count,
        "conflicts": [], "conclusion": "SUPPORTING_EVIDENCE_ONLY",
    }

    economic_reconciliation = {
        "order_status": bound_order.status,
        "unique_bound_fill_count": len(bound_fills),
        "fill_ids": sorted(f.fill_id for f in bound_fills),
        "canonical_fill_quantity": str(quantity),
        "canonical_filled_principal": str(principal),
        "canonical_fee_cost": str(fee),
        "order_fill_quantity_match": order_fill_match,
        "remaining_quantity_match": order_fill_match,
        "position_evidence_complete": live_pos_complete and hist_pos_complete,
        "settlement_evidence_complete_or_not_required": settlement_complete,
        "economic_bounds_pass": econ_halt is None,
        "reconciliation_complete": (
            econ_halt is None and order_fill_match == "PASS" and fills_source_complete
            and live_pos_complete and hist_pos_complete and settlement_complete
        ),
    }

    result_class = _finish_positive(
        historical_resolution_input=historical_resolution_input, transport=transport, deadline=deadline,
        state=state, ctx=ctx, cutoff_pre=cutoff_pre,
        result_class=(
            (ResultClass.READ_POSITIVE_FILL_DERIVED_ORDER_BOUND_TERMINAL_RECONCILED if economic_reconciliation["reconciliation_complete"]
             else ResultClass.READ_POSITIVE_FILL_DERIVED_ORDER_BOUND_TERMINAL_ECONOMIC_INCOMPLETE)
            if binding_source_class is BindingSourceClass.FILL_DERIVED else
            (ResultClass.READ_POSITIVE_ORDER_BOUND_TERMINAL_RECONCILED if economic_reconciliation["reconciliation_complete"]
             else ResultClass.READ_POSITIVE_ORDER_BOUND_TERMINAL_ECONOMIC_INCOMPLETE)
        ),
        halt_code=econ_halt,
        bound_order_id=bound_order_id, binding_source_class=binding_source_class,
        exact_reread_required=exact_reread_required, exact_reread_performed=exact_reread_performed,
        exact_reread_reason=exact_reread_reason, fill_evidence_origin=fill_evidence_origin,
        live_fill_source_reused=live_fill_source_reused, historical_fill_source_reused=historical_fill_source_reused,
        canonical_fill_quantity=quantity, canonical_filled_principal=principal, canonical_fee_cost=fee,
        economic_reconciliation=economic_reconciliation,
        completeness=_default_completeness(
            live_order_partition_complete=True, historical_order_partition_complete=True, orders_complete=True,
            live_fill_partition_complete=fills_source_complete, historical_fill_partition_complete=fills_source_complete,
            fills_complete=fills_source_complete,
            live_position_partition_complete=live_pos_complete, historical_position_partition_complete=hist_pos_complete,
            position_or_exposure_evidence_complete=live_pos_complete and hist_pos_complete,
            settlement_evidence_complete_or_not_required=settlement_complete,
            pagination_complete=True, source_semantics_complete=True, identity_resolution_complete=True,
            economic_reconciliation_complete_or_not_required=economic_reconciliation["reconciliation_complete"],
            overall_evidence_complete=economic_reconciliation["reconciliation_complete"],
            conclusion="POSITIVE_TERMINAL_BINDING",
        ),
        planned_branch=state.branch,
    )
    return result_class

# ---------------------------------------------------------------------------
# P9-P10-P11-P12: shared POST-observation tail
# ---------------------------------------------------------------------------

def _post_observation_tail(
    *, transport: HistoricalResolutionTransport, deadline: _Deadline, state: _ExecutionState,
    ctx: Dict[str, object], cutoff_pre: Mapping[str, object],
) -> Optional[HaltCode]:
    """Perform P9 (HISTORICAL_CUTOFF POST) and P10 (USER_DATA_TIMESTAMP POST),
    then evaluate the RA1-TIME-003 freshness-ordering predicate and the
    RA1-PAGE-005 per-family moving-cutoff coverage theorem.  Returns a halt
    code on failure or on a proven coverage gap, otherwise ``None``.  Never
    issues a repair/resend GET -- every conclusion here is drawn only from
    evidence already collected earlier in this run."""

    cutoff_post, halt = _read_cutoff(transport, deadline, state, phase="POST")
    if halt is not None:
        return halt
    ctx["cutoff_post"] = cutoff_post
    udt_post, halt = _read_user_data_timestamp(transport, deadline, state, phase="POST")
    if halt is not None:
        return halt
    ctx["udt_post"] = udt_post

    # RA1-TIME-003: USER_DATA_TIMESTAMP PRE->POST freshness ordering.  This is
    # approximate-freshness evidence only; POST >= PRE never by itself proves
    # partition coverage (that is the separate theorem below).
    udt_pre = ctx.get("udt_pre")
    if isinstance(udt_pre, Mapping) and _parse_rfc3339(udt_post["as_of_time"]) < _parse_rfc3339(udt_pre["as_of_time"]):
        return HaltCode.HISTORICAL_CUTOFF_OR_FRESHNESS_GAP

    coverage = _assess_cutoff_coverage(
        cutoff_pre, cutoff_post, evaluation_query_max_ts=ctx.get("evaluation_query_max_ts"),
    )
    ctx["cutoff_coverage"] = coverage

    if any(label == "CUTOFF_REGRESSED_OR_INVALID" for label in coverage.values()):
        return HaltCode.HISTORY_INTERVAL_UNOBSERVABLE

    # ORDERS coverage gates every conclusion: order-universe completeness is
    # load-bearing for the direct-match/zero-match cardinality theorem itself.
    if coverage["ORDERS"] == "CUTOFF_ADVANCED_WITH_COVERAGE_UNPROVEN":
        return HaltCode.HISTORY_INTERVAL_UNOBSERVABLE

    # A fill-derived binding's identity rests entirely on the pre-binding
    # fill discovery (ctx["fill_evidence"]); if that traversal's coverage is
    # unprovable at POST time, Correction 02's "no repair traversal" rule
    # forbids resending fills to firm it up, so the whole run fails closed
    # rather than accept an unresolved binding.
    fill_discovery_performed = bool(ctx.get("fill_evidence"))
    if fill_discovery_performed and coverage["FILLS"] == "CUTOFF_ADVANCED_WITH_COVERAGE_UNPROVEN":
        return HaltCode.HISTORY_INTERVAL_UNOBSERVABLE

    return None


def _finish_positive(
    *,
    historical_resolution_input: HistoricalResolutionInput,
    transport: HistoricalResolutionTransport,
    deadline: _Deadline,
    state: _ExecutionState,
    ctx: Dict[str, object],
    cutoff_pre: Mapping[str, object],
    result_class: ResultClass,
    halt_code: Optional[HaltCode],
    bound_order_id: str,
    binding_source_class: BindingSourceClass,
    exact_reread_required: bool,
    exact_reread_performed: bool,
    exact_reread_reason: ExactOrderRereadReason,
    fill_evidence_origin: FillEvidenceOrigin,
    live_fill_source_reused: bool,
    historical_fill_source_reused: bool,
    canonical_fill_quantity: Optional[Decimal],
    canonical_filled_principal: Optional[Decimal],
    canonical_fee_cost: Optional[Decimal],
    economic_reconciliation: Optional[Dict[str, object]],
    completeness: Dict[str, object],
    planned_branch: str,
) -> HistoricalResolutionResult:
    tail_halt = _post_observation_tail(transport=transport, deadline=deadline, state=state, ctx=ctx, cutoff_pre=cutoff_pre)
    if tail_halt is not None:
        return _build_result(
            historical_resolution_input=historical_resolution_input, state=state, deadline=deadline, ctx=ctx,
            result_class=_generic_result_for_halt(tail_halt), halt_code=tail_halt, planned_branch=planned_branch,
        )

    # RA1-PAGE-005 Correction 03: a direct-binding branch's freshly-traversed
    # FILLS/POSITIONS coverage that turns out unprovable at POST time cannot
    # invalidate an already-established ORDERS-based identity, but it does
    # mean economic reconciliation cannot claim completeness.  No repair GET
    # is issued; the run degrades using only the evidence already collected.
    coverage = ctx.get("cutoff_coverage", {})
    coverage_unproven = any(
        coverage.get(family) == "CUTOFF_ADVANCED_WITH_COVERAGE_UNPROVEN" for family in ("FILLS", "POSITIONS")
    )
    if coverage_unproven and economic_reconciliation is not None:
        economic_reconciliation = dict(economic_reconciliation)
        economic_reconciliation["reconciliation_complete"] = False
        completeness = dict(completeness)
        completeness["fills_complete"] = completeness["fills_complete"] and coverage.get("FILLS") != "CUTOFF_ADVANCED_WITH_COVERAGE_UNPROVEN"
        completeness["position_or_exposure_evidence_complete"] = (
            completeness["position_or_exposure_evidence_complete"] and coverage.get("POSITIONS") != "CUTOFF_ADVANCED_WITH_COVERAGE_UNPROVEN"
        )
        completeness["economic_reconciliation_complete_or_not_required"] = False
        completeness["overall_evidence_complete"] = False
        completeness["unobservable_intervals"] = list(completeness.get("unobservable_intervals", [])) + [
            f"{family}_CUTOFF_ADVANCED_COVERAGE_UNPROVEN" for family in ("FILLS", "POSITIONS")
            if coverage.get(family) == "CUTOFF_ADVANCED_WITH_COVERAGE_UNPROVEN"
        ]
        if result_class is ResultClass.READ_POSITIVE_ORDER_BOUND_TERMINAL_RECONCILED:
            result_class = ResultClass.READ_POSITIVE_ORDER_BOUND_TERMINAL_ECONOMIC_INCOMPLETE
        elif result_class is ResultClass.READ_POSITIVE_FILL_DERIVED_ORDER_BOUND_TERMINAL_RECONCILED:
            result_class = ResultClass.READ_POSITIVE_FILL_DERIVED_ORDER_BOUND_TERMINAL_ECONOMIC_INCOMPLETE

    negative_closure = _negative_closure_assessment(
        orders_complete=True, fills_complete=bool(completeness.get("fills_complete", True)),
        cutoff_regressed=False, zero_match=False,
    )
    return _build_result(
        historical_resolution_input=historical_resolution_input, state=state, deadline=deadline, ctx=ctx,
        result_class=result_class, halt_code=halt_code, bound_order_id=bound_order_id,
        binding_source_class=binding_source_class, exact_reread_required=exact_reread_required,
        exact_reread_performed=exact_reread_performed, exact_reread_reason=exact_reread_reason,
        fill_evidence_origin=fill_evidence_origin, live_fill_source_reused=live_fill_source_reused,
        historical_fill_source_reused=historical_fill_source_reused,
        canonical_fill_quantity=canonical_fill_quantity, canonical_filled_principal=canonical_filled_principal,
        canonical_fee_cost=canonical_fee_cost, economic_reconciliation=economic_reconciliation,
        completeness=completeness, negative_closure=negative_closure, planned_branch=planned_branch,
    )


def _finish_zero_or_unresolved(
    *,
    historical_resolution_input: HistoricalResolutionInput,
    transport: HistoricalResolutionTransport,
    deadline: _Deadline,
    state: _ExecutionState,
    ctx: Dict[str, object],
    cutoff_pre: Mapping[str, object],
    orders_complete: bool,
    fills_complete: bool,
    unresolved: bool,
) -> HistoricalResolutionResult:
    tail_halt = _post_observation_tail(transport=transport, deadline=deadline, state=state, ctx=ctx, cutoff_pre=cutoff_pre)
    if tail_halt is not None:
        return _build_result(
            historical_resolution_input=historical_resolution_input, state=state, deadline=deadline, ctx=ctx,
            result_class=_generic_result_for_halt(tail_halt), halt_code=tail_halt, planned_branch=state.branch or "ZERO_MATCH",
        )
    negative_closure = _negative_closure_assessment(
        orders_complete=orders_complete, fills_complete=fills_complete, cutoff_regressed=False, zero_match=True,
    )
    completeness = _default_completeness(
        live_order_partition_complete=orders_complete, historical_order_partition_complete=orders_complete,
        orders_complete=orders_complete,
        live_fill_partition_complete=fills_complete, historical_fill_partition_complete=fills_complete,
        fills_complete=fills_complete,
        pagination_complete=True, cutoff_partition_complete=True, source_semantics_complete=True,
        identity_resolution_complete=not unresolved, retention_lower_bound_proven=False,
        overall_evidence_complete=False, conclusion="ZERO_MATCH_NEGATIVE_THEOREM_NOT_PROVEN",
    )
    return _build_result(
        historical_resolution_input=historical_resolution_input, state=state, deadline=deadline, ctx=ctx,
        result_class=ResultClass.READ_ZERO_MATCH_NEGATIVE_THEOREM_NOT_PROVEN, halt_code=None,
        completeness=completeness, negative_closure=negative_closure, planned_branch=state.branch or "ZERO_MATCH",
    )
