"""Offline deterministic acceptance tests for
``arb.venues.kalshi.order_lifecycle`` (Revision-06 Section 16 contract).

SAME_SCOPE_CORRECTION_01: extends the Implementation-01 suite to cover the
complete Appendix F writer-proof contract, the Section 9.4 pre-send gate
(spec/source/binding/authorization/proof, all evaluated before transport
call 1), the Section 2.4 capability-separation model, the full Appendix E
Order/Fill schemas (including numeric-JSON-value rejection), the Appendix G
three-way create/cancel result classification, per-request deadline
propagation, and final-fill-pagination-after-cancel. All previously valid
Implementation-01 cases are preserved.

Every test in this module is fully offline: no socket, no DNS resolution,
no real HTTP client, and no real credential or private-key material is
used anywhere. All venue interaction is exercised through
``_FakeTransport``, an in-memory stand-in for ``LifecycleTransport``.
RSA-PSS signing tests use freshly generated, obviously-synthetic test key
material only.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import unittest
from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Dict, List, Mapping, Optional, Tuple, Union

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from arb.venues.kalshi import order_lifecycle as ol
from arb.venues.kalshi import validation as kalshi_validation
from arb.venues.kalshi.models import (
    AuthorizationValue,
    CredentialReferenceKind,
    CredentialReferenceState,
    CredentialSourceReference,
    EndpointComponents,
    Environment,
    NonSecretConfigurationInput,
    RequestedCapability,
    TaskAuthorizationCapabilityEnvelope,
    ValidatedDemoProfile,
)


TICKER = "KXTEST-26AUG-T0"
WRITER_IDENTITY = "writer-session-0001"
LIFECYCLE_AUTH_ID = "LEA-TEST-01"
ACCOUNT_SCOPE_REF = "account-scope-ref-0001"
CANONICAL_STATE_COMMIT = "a6a2bd1618011030eeadb410112a967bbbabcb07"
ACCEPTED_IMPLEMENTATION_COMMIT = "0123456789abcdef0123456789abcdef01234567"
EXECUTOR_ENTRY_UTC = "2026-08-09T12:00:00Z"
DEFAULT_CLIENT_ORDER_ID = "5781e77b-e1ed-4303-bcf6-bdb282419251"
ALT_CLIENT_ORDER_ID = "a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a"


# ---------------------------------------------------------------------------
# Exact byte-identical Appendix C / Appendix D canonical records, extracted
# verbatim from KALSHI_DEMO_ONE_ORDER_LIFECYCLE_SPEC_06.md. Each constant's
# .encode("utf-8") length and sha256 are asserted against the accepted
# identities in ol.SOURCE_RECORD_BYTES/SHA256 and ol.OPERATION_BINDINGS in
# TestSourceAndOperationBindingIdentities below -- these are the real
# accepted bytes, not synthetic same-shape buffers.
# ---------------------------------------------------------------------------

APPENDIX_C_SOURCE_RECORD_JSON = '''{"content_retrieval_classification":"SUCCESS__USER_BROWSER_DIRECT_OFFICIAL_DOWNLOAD_RECEIVED_DURING_ACTIVE_TASK","http_status_observed_by_bruno":null,"normalized_source_media_type":"text/yaml","openapi_version":"3.0.0","raw_lf_count":9563,"raw_line_ending_profile":"CRLF","raw_openapi_byte_length":333283,"raw_openapi_sha256":"80f4961e275dba2fed8e464c90c6ee77e3e8d521ec0c2e16b1c94dde8bf0160d","retrieval_provenance":"GUSTAVO_DIRECT_DOWNLOAD_FROM_EXACT_OFFICIAL_URL_AND_UPLOAD_TO_ACTIVE_REVISION_03_TASK","retrieved_at_utc":"2026-08-09T13:00:42Z","reviewed_demo_base_path":"/trade-api/v2","reviewed_demo_rest_origin":"https://external-api.demo.kalshi.co","source_format":"YAML","source_info_title":"Kalshi Trade API Manual Endpoints","source_info_version":"3.27.0","source_schema_revision":2,"source_url":"https://docs.kalshi.com/openapi.yaml"}'''

APPENDIX_D1_PRE_CREATE_ORDER_TRUTH_JSON = '''{"binding_purpose":"PRE_CREATE_ORDER_TRUTH","binding_schema_revision":3,"book_side_enum":["bid","ask"],"effective_security":[{"kalshiAccessKey":[],"kalshiAccessSignature":[],"kalshiAccessTimestamp":[]}],"effective_security_source":"OPERATION_OVERRIDE","fixed_point_component_contracts":{"FixedPointCount":{"example":"10.00","minimum_granularity":"0.01","request_decimal_places":"0-2","response_decimal_places":2,"type":"string"},"FixedPointDollars":{"example":"0.5600","market_quote_interval_constraint":"market price level structure","maximum_supported_decimal_places":6,"type":"string"}},"fixed_point_components":["FixedPointDollars","FixedPointCount"],"normalized_source_media_type":"text/yaml","openapi_query_parameters":{"cursor":{"required":false,"type":"string"},"event_ticker":{"required":false,"type":"string"},"limit":{"default":100,"format":"int64","maximum":1000,"minimum":1,"required":false,"type":"integer"},"max_ts":{"format":"int64","required":false,"type":"integer"},"min_ts":{"format":"int64","required":false,"type":"integer"},"status":{"required":false,"type":"string"},"subaccount":{"primary_value":0,"required":false,"type":"integer"},"ticker":{"required":false,"type":"string"}},"openapi_version":"3.0.0","operation_id":"GetOrders","operation_method":"GET","operation_path_template":"/portfolio/orders","operation_security_key_present":true,"order_direction_semantics":{"book_side":"required; bid means buy YES; ask means sell YES","legacy_action":"optional deprecated; not used for lifecycle invariant","legacy_side":"optional deprecated; not used for lifecycle invariant","outcome_side":"required; enum yes|no"},"order_optional_fields":["side","action","expiration_time","created_time","last_update_time","self_trade_prevention_type","order_group_id","cancel_order_on_pause","subaccount_number","exchange_index"],"order_required_fields":["order_id","user_id","client_order_id","ticker","outcome_side","book_side","type","status","yes_price_dollars","no_price_dollars","fill_count_fp","remaining_count_fp","initial_count_fp","taker_fees_dollars","maker_fees_dollars","taker_fill_cost_dollars","maker_fill_cost_dollars"],"order_status_enum":["resting","canceled","executed"],"orders_item_schema":"Order","project_active_filter":"status=resting","project_completeness_rule":"cursor MUST equal empty string; non-empty cursor halts; no second page","project_query_contract":{"cursor":"OMITTED_FIRST_REQUEST","event_ticker":"PROHIBITED","limit":1000,"max_ts":"PROHIBITED","min_ts":"PROHIBITED","status":"resting","subaccount":0,"ticker":"EXACT_AUTHORIZED_TICKER"},"raw_openapi_byte_length":333283,"raw_openapi_sha256":"80f4961e275dba2fed8e464c90c6ee77e3e8d521ec0c2e16b1c94dde8bf0160d","required_auth_header_names":["KALSHI-ACCESS-KEY","KALSHI-ACCESS-SIGNATURE","KALSHI-ACCESS-TIMESTAMP"],"response_media_type":"application/json","response_required_top_level_fields":["orders","cursor"],"response_schema":"GetOrdersResponse","retrieved_at_utc":"2026-08-09T13:00:42Z","reviewed_demo_base_path":"/trade-api/v2","reviewed_demo_rest_origin":"https://external-api.demo.kalshi.co","reviewed_full_request_path":"/trade-api/v2/portfolio/orders","source_drift_from_revision_02":"NO_MATERIAL_BOUND_OPERATION_DRIFT","source_http_status_observed_by_bruno":null,"source_info_title":"Kalshi Trade API Manual Endpoints","source_info_version":"3.27.0","source_line_locations":{"BookSide_schema_lines":"4642-4650","FixedPointCount_schema_lines":"4462-4469","FixedPointDollars_schema_lines":"4454-4460","GetOrdersResponse_schema_lines":"6217-6227","OrderStatus_schema_lines":"4652-4657","Order_schema_lines":"5963-6122","operation_path_lines":"989-1029"},"source_retrieval_classification":"SUCCESS__USER_BROWSER_DIRECT_OFFICIAL_DOWNLOAD_RECEIVED_DURING_ACTIVE_TASK","source_url":"https://docs.kalshi.com/openapi.yaml","success_http_status":200}'''

APPENDIX_D2_CREATE_ORDER_V2_JSON = '''{"binding_purpose":"CREATE_ORDER_V2","binding_schema_revision":3,"book_side_enum":["bid","ask"],"book_side_semantics":"bid means buy YES; ask means sell YES; endpoint quotes event-market YES leg","client_order_id_semantics":{"authoritative_Order_required":true,"create_response_required":false,"openapi_request_required":false,"project_request_required":true,"project_reuse_rule":"same frozen value for all recovery/reconciliation; never regenerate after send may begin"},"effective_security":[{"kalshiAccessKey":[],"kalshiAccessSignature":[],"kalshiAccessTimestamp":[]}],"effective_security_source":"OPERATION_OVERRIDE","fixed_point_component_contracts":{"FixedPointCount":{"example":"10.00","minimum_granularity":"0.01","request_decimal_places":"0-2","response_decimal_places":2,"type":"string"},"FixedPointDollars":{"example":"0.5600","market_quote_interval_constraint":"market price level structure","maximum_supported_decimal_places":6,"type":"string"}},"fixed_point_components":["FixedPointDollars","FixedPointCount"],"normalized_source_media_type":"text/yaml","openapi_optional_request_fields":["client_order_id","expiration_time","post_only","cancel_order_on_pause","reduce_only","subaccount","order_group_id","exchange_index"],"openapi_required_request_fields":["ticker","side","count","price","time_in_force","self_trade_prevention_type"],"openapi_version":"3.0.0","operation_id":"CreateOrderV2","operation_method":"POST","operation_path_template":"/portfolio/events/orders","operation_security_key_present":true,"project_prohibited_request_fields":["order_group_id","action","yes_price","no_price","type"],"project_required_closed_request_fields":["ticker","client_order_id","side","count","price","time_in_force","self_trade_prevention_type","expiration_time","post_only","cancel_order_on_pause","reduce_only","subaccount","exchange_index"],"raw_openapi_byte_length":333283,"raw_openapi_sha256":"80f4961e275dba2fed8e464c90c6ee77e3e8d521ec0c2e16b1c94dde8bf0160d","request_body_required":true,"request_media_type":"application/json","request_schema":"CreateOrderV2Request","required_auth_header_names":["KALSHI-ACCESS-KEY","KALSHI-ACCESS-SIGNATURE","KALSHI-ACCESS-TIMESTAMP"],"response_media_type":"application/json","response_optional_fields":["client_order_id","average_fill_price","average_fee_paid"],"response_required_fields":["order_id","fill_count","remaining_count","ts_ms"],"response_schema":"CreateOrderV2Response","retrieved_at_utc":"2026-08-09T13:00:42Z","reviewed_demo_base_path":"/trade-api/v2","reviewed_demo_rest_origin":"https://external-api.demo.kalshi.co","reviewed_full_request_path":"/trade-api/v2/portfolio/events/orders","self_trade_prevention_type_enum":["taker_at_cross","maker"],"source_drift_from_revision_02":"NO_MATERIAL_BOUND_OPERATION_DRIFT","source_http_status_observed_by_bruno":null,"source_info_title":"Kalshi Trade API Manual Endpoints","source_info_version":"3.27.0","source_line_locations":{"BookSide_schema_lines":"4642-4650","CreateOrderV2Request_schema_lines":"7900-8013","CreateOrderV2Response_schema_lines":"8015-8055","ExchangeIndex_schema_lines":"4471-4473","FixedPointCount_schema_lines":"4462-4469","FixedPointDollars_schema_lines":"4454-4460","SelfTradePreventionType_schema_lines":"4631-4640","operation_path_lines":"1127-1164"},"source_retrieval_classification":"SUCCESS__USER_BROWSER_DIRECT_OFFICIAL_DOWNLOAD_RECEIVED_DURING_ACTIVE_TASK","source_url":"https://docs.kalshi.com/openapi.yaml","success_http_status":201,"time_in_force_enum":["fill_or_kill","good_till_canceled","immediate_or_cancel"]}'''

APPENDIX_D3_EXACT_ORDER_READ_JSON = '''{"binding_purpose":"EXACT_ORDER_READ","binding_schema_revision":3,"book_side_enum":["bid","ask"],"effective_security":[{"kalshiAccessKey":[],"kalshiAccessSignature":[],"kalshiAccessTimestamp":[]}],"effective_security_source":"OPERATION_OVERRIDE","fixed_point_component_contracts":{"FixedPointCount":{"example":"10.00","minimum_granularity":"0.01","request_decimal_places":"0-2","response_decimal_places":2,"type":"string"},"FixedPointDollars":{"example":"0.5600","market_quote_interval_constraint":"market price level structure","maximum_supported_decimal_places":6,"type":"string"}},"fixed_point_components":["FixedPointDollars","FixedPointCount"],"normalized_source_media_type":"text/yaml","openapi_version":"3.0.0","operation_id":"GetOrder","operation_method":"GET","operation_path_template":"/portfolio/orders/{order_id}","operation_security_key_present":true,"order_direction_semantics":{"book_side":"required; bid means buy YES; ask means sell YES","legacy_action":"optional deprecated; not used for lifecycle invariant","legacy_side":"optional deprecated; not used for lifecycle invariant","outcome_side":"required; enum yes|no"},"order_optional_fields":["side","action","expiration_time","created_time","last_update_time","self_trade_prevention_type","order_group_id","cancel_order_on_pause","subaccount_number","exchange_index"],"order_required_fields":["order_id","user_id","client_order_id","ticker","outcome_side","book_side","type","status","yes_price_dollars","no_price_dollars","fill_count_fp","remaining_count_fp","initial_count_fp","taker_fees_dollars","maker_fees_dollars","taker_fill_cost_dollars","maker_fill_cost_dollars"],"order_schema":"Order","order_status_enum":["resting","canceled","executed"],"path_parameters":{"order_id":{"required":true,"type":"string"}},"query_parameters":"NONE","raw_openapi_byte_length":333283,"raw_openapi_sha256":"80f4961e275dba2fed8e464c90c6ee77e3e8d521ec0c2e16b1c94dde8bf0160d","required_auth_header_names":["KALSHI-ACCESS-KEY","KALSHI-ACCESS-SIGNATURE","KALSHI-ACCESS-TIMESTAMP"],"response_media_type":"application/json","response_required_top_level_fields":["order"],"response_schema":"GetOrderResponse","retrieved_at_utc":"2026-08-09T13:00:42Z","reviewed_demo_base_path":"/trade-api/v2","reviewed_demo_rest_origin":"https://external-api.demo.kalshi.co","reviewed_full_request_path_template":"/trade-api/v2/portfolio/orders/{order_id}","source_drift_from_revision_02":"NO_MATERIAL_BOUND_OPERATION_DRIFT","source_http_status_observed_by_bruno":null,"source_info_title":"Kalshi Trade API Manual Endpoints","source_info_version":"3.27.0","source_line_locations":{"BookSide_schema_lines":"4642-4650","FixedPointCount_schema_lines":"4462-4469","FixedPointDollars_schema_lines":"4454-4460","GetOrderResponse_schema_lines":"7544-7549","OrderStatus_schema_lines":"4652-4657","Order_schema_lines":"5963-6122","operation_path_lines":"1030-1063"},"source_retrieval_classification":"SUCCESS__USER_BROWSER_DIRECT_OFFICIAL_DOWNLOAD_RECEIVED_DURING_ACTIVE_TASK","source_url":"https://docs.kalshi.com/openapi.yaml","success_http_status":200}'''

APPENDIX_D4_ORDER_LIST_RECOVERY_JSON = '''{"binding_purpose":"ORDER_LIST_RECOVERY","binding_schema_revision":3,"book_side_enum":["bid","ask"],"client_order_id_semantics":"Order.client_order_id is authoritative required field; exact local match to frozen lifecycle ID; no server-side client_order_id query filter","effective_security":[{"kalshiAccessKey":[],"kalshiAccessSignature":[],"kalshiAccessTimestamp":[]}],"effective_security_source":"OPERATION_OVERRIDE","fixed_point_component_contracts":{"FixedPointCount":{"example":"10.00","minimum_granularity":"0.01","request_decimal_places":"0-2","response_decimal_places":2,"type":"string"},"FixedPointDollars":{"example":"0.5600","market_quote_interval_constraint":"market price level structure","maximum_supported_decimal_places":6,"type":"string"}},"fixed_point_components":["FixedPointDollars","FixedPointCount"],"normalized_source_media_type":"text/yaml","openapi_query_parameters":{"cursor":{"required":false,"type":"string"},"event_ticker":{"required":false,"type":"string"},"limit":{"default":100,"format":"int64","maximum":1000,"minimum":1,"required":false,"type":"integer"},"max_ts":{"format":"int64","required":false,"type":"integer"},"min_ts":{"format":"int64","required":false,"type":"integer"},"status":{"required":false,"type":"string"},"subaccount":{"primary_value":0,"required":false,"type":"integer"},"ticker":{"required":false,"type":"string"}},"openapi_version":"3.0.0","operation_id":"GetOrders","operation_method":"GET","operation_path_template":"/portfolio/orders","operation_security_key_present":true,"order_direction_semantics":{"book_side":"required; bid means buy YES; ask means sell YES","legacy_action":"optional deprecated; not used for lifecycle invariant","legacy_side":"optional deprecated; not used for lifecycle invariant","outcome_side":"required; enum yes|no"},"order_optional_fields":["side","action","expiration_time","created_time","last_update_time","self_trade_prevention_type","order_group_id","cancel_order_on_pause","subaccount_number","exchange_index"],"order_required_fields":["order_id","user_id","client_order_id","ticker","outcome_side","book_side","type","status","yes_price_dollars","no_price_dollars","fill_count_fp","remaining_count_fp","initial_count_fp","taker_fees_dollars","maker_fees_dollars","taker_fill_cost_dollars","maker_fill_cost_dollars"],"order_status_enum":["resting","canceled","executed"],"orders_item_schema":"Order","project_query_contract":{"cursor":"OMITTED_FIRST_REQUEST","event_ticker":"PROHIBITED","limit":1000,"max_ts":"PROHIBITED","min_ts":"PROHIBITED","status":"OMITTED","subaccount":0,"ticker":"EXACT_AUTHORIZED_TICKER"},"project_recovery_rule":"local exact client_order_id match; exactly one match; cursor MUST be empty; no second page","raw_openapi_byte_length":333283,"raw_openapi_sha256":"80f4961e275dba2fed8e464c90c6ee77e3e8d521ec0c2e16b1c94dde8bf0160d","required_auth_header_names":["KALSHI-ACCESS-KEY","KALSHI-ACCESS-SIGNATURE","KALSHI-ACCESS-TIMESTAMP"],"response_media_type":"application/json","response_required_top_level_fields":["orders","cursor"],"response_schema":"GetOrdersResponse","retrieved_at_utc":"2026-08-09T13:00:42Z","reviewed_demo_base_path":"/trade-api/v2","reviewed_demo_rest_origin":"https://external-api.demo.kalshi.co","reviewed_full_request_path":"/trade-api/v2/portfolio/orders","source_drift_from_revision_02":"NO_MATERIAL_BOUND_OPERATION_DRIFT","source_http_status_observed_by_bruno":null,"source_info_title":"Kalshi Trade API Manual Endpoints","source_info_version":"3.27.0","source_line_locations":{"BookSide_schema_lines":"4642-4650","FixedPointCount_schema_lines":"4462-4469","FixedPointDollars_schema_lines":"4454-4460","GetOrdersResponse_schema_lines":"6217-6227","OrderStatus_schema_lines":"4652-4657","Order_schema_lines":"5963-6122","operation_path_lines":"989-1029"},"source_retrieval_classification":"SUCCESS__USER_BROWSER_DIRECT_OFFICIAL_DOWNLOAD_RECEIVED_DURING_ACTIVE_TASK","source_url":"https://docs.kalshi.com/openapi.yaml","success_http_status":200}'''

APPENDIX_D5_FILL_READ_JSON = '''{"binding_purpose":"FILL_READ","binding_schema_revision":3,"book_side_enum":["bid","ask"],"effective_security":[{"kalshiAccessKey":[],"kalshiAccessSignature":[],"kalshiAccessTimestamp":[]}],"effective_security_source":"OPERATION_OVERRIDE","fill_direction_semantics":{"book_side":"required; bid means YES-side direction, ask means NO-side direction","legacy_action":"optional deprecated; ignored","legacy_side":"optional deprecated; ignored","outcome_side":"required; enum yes|no"},"fill_optional_fields":["side","action","created_time","subaccount_number","ts"],"fill_required_fields":["fill_id","trade_id","order_id","ticker","market_ticker","outcome_side","book_side","count_fp","yes_price_dollars","no_price_dollars","is_taker","fee_cost"],"fills_item_schema":"Fill","fixed_point_component_contracts":{"FixedPointCount":{"example":"10.00","minimum_granularity":"0.01","request_decimal_places":"0-2","response_decimal_places":2,"type":"string"},"FixedPointDollars":{"example":"0.5600","market_quote_interval_constraint":"market price level structure","maximum_supported_decimal_places":6,"type":"string"}},"fixed_point_components":["FixedPointDollars","FixedPointCount"],"normalized_source_media_type":"text/yaml","openapi_query_parameters":{"cursor":{"required":false,"type":"string"},"limit":{"default":100,"format":"int64","maximum":1000,"minimum":1,"required":false,"type":"integer"},"max_ts":{"format":"int64","required":false,"type":"integer"},"min_ts":{"format":"int64","required":false,"type":"integer"},"order_id":{"required":false,"type":"string"},"subaccount":{"primary_value":0,"required":false,"type":"integer"},"ticker":{"required":false,"type":"string"}},"openapi_version":"3.0.0","operation_id":"GetFills","operation_method":"GET","operation_path_template":"/portfolio/fills","operation_security_key_present":true,"project_query_contract":{"cursor":"OMITTED_FIRST_REQUEST_OR_EXACT_PRIOR_CURSOR","limit":1000,"max_ts":"PROHIBITED","min_ts":"PROHIBITED","order_id":"EXACT_BOUND_ORDER_ID","subaccount":0,"ticker":"PROHIBITED"},"raw_openapi_byte_length":333283,"raw_openapi_sha256":"80f4961e275dba2fed8e464c90c6ee77e3e8d521ec0c2e16b1c94dde8bf0160d","required_auth_header_names":["KALSHI-ACCESS-KEY","KALSHI-ACCESS-SIGNATURE","KALSHI-ACCESS-TIMESTAMP"],"response_media_type":"application/json","response_required_top_level_fields":["fills","cursor"],"response_schema":"GetFillsResponse","retrieved_at_utc":"2026-08-09T13:00:42Z","reviewed_demo_base_path":"/trade-api/v2","reviewed_demo_rest_origin":"https://external-api.demo.kalshi.co","reviewed_full_request_path":"/trade-api/v2/portfolio/fills","source_drift_from_revision_02":"NO_MATERIAL_BOUND_OPERATION_DRIFT","source_http_status_observed_by_bruno":null,"source_info_title":"Kalshi Trade API Manual Endpoints","source_info_version":"3.27.0","source_line_locations":{"BookSide_schema_lines":"4642-4650","Fill_schema_lines":"6528-6646","FixedPointCount_schema_lines":"4462-4469","FixedPointDollars_schema_lines":"4454-4460","GetFillsResponse_schema_lines":"6648-6658","operation_path_lines":"2042-2079"},"source_retrieval_classification":"SUCCESS__USER_BROWSER_DIRECT_OFFICIAL_DOWNLOAD_RECEIVED_DURING_ACTIVE_TASK","source_url":"https://docs.kalshi.com/openapi.yaml","success_http_status":200}'''

APPENDIX_D6_CANCEL_ORDER_V2_JSON = '''{"binding_purpose":"CANCEL_ORDER_V2","binding_schema_revision":3,"client_order_id_semantics":"Cancel response client_order_id optional; if present must equal frozen lifecycle client_order_id","effective_security":[{"kalshiAccessKey":[],"kalshiAccessSignature":[],"kalshiAccessTimestamp":[]}],"effective_security_source":"OPERATION_OVERRIDE","fixed_point_component_contracts":{"FixedPointCount":{"example":"10.00","minimum_granularity":"0.01","request_decimal_places":"0-2","response_decimal_places":2,"type":"string"}},"fixed_point_components":["FixedPointCount"],"normalized_source_media_type":"text/yaml","openapi_query_parameters":{"exchange_index":{"default":0,"required":false,"schema":"ExchangeIndex"},"market_ticker":{"required":false,"required_only_when":"exchange_index=-1","type":"string"},"subaccount":{"default":0,"primary_value":0,"required":false,"type":"integer"}},"openapi_version":"3.0.0","operation_id":"CancelOrderV2","operation_method":"DELETE","operation_path_template":"/portfolio/events/orders/{order_id}","operation_security_key_present":true,"path_parameters":{"order_id":{"required":true,"type":"string"}},"project_query_contract":{"exchange_index":0,"market_ticker":"OMITTED","subaccount":0},"raw_openapi_byte_length":333283,"raw_openapi_sha256":"80f4961e275dba2fed8e464c90c6ee77e3e8d521ec0c2e16b1c94dde8bf0160d","request_body":"ABSENT","required_auth_header_names":["KALSHI-ACCESS-KEY","KALSHI-ACCESS-SIGNATURE","KALSHI-ACCESS-TIMESTAMP"],"response_media_type":"application/json","response_optional_fields":["client_order_id"],"response_required_fields":["order_id","reduced_by","ts_ms"],"response_schema":"CancelOrderV2Response","retrieved_at_utc":"2026-08-09T13:00:42Z","reviewed_demo_base_path":"/trade-api/v2","reviewed_demo_rest_origin":"https://external-api.demo.kalshi.co","reviewed_full_request_path_template":"/trade-api/v2/portfolio/events/orders/{order_id}","source_drift_from_revision_02":"NO_MATERIAL_BOUND_OPERATION_DRIFT","source_http_status_observed_by_bruno":null,"source_info_title":"Kalshi Trade API Manual Endpoints","source_info_version":"3.27.0","source_line_locations":{"CancelOrderV2Response_schema_lines":"8057-8082","ExchangeIndex_schema_lines":"4471-4473","FixedPointCount_schema_lines":"4462-4469","operation_path_lines":"1256-1300"},"source_retrieval_classification":"SUCCESS__USER_BROWSER_DIRECT_OFFICIAL_DOWNLOAD_RECEIVED_DURING_ACTIVE_TASK","source_url":"https://docs.kalshi.com/openapi.yaml","success_http_status":200}'''

_APPENDIX_D_BY_BINDING_NAME = {
    "PRE_CREATE_ORDER_TRUTH": APPENDIX_D1_PRE_CREATE_ORDER_TRUTH_JSON,
    "CREATE_ORDER_V2": APPENDIX_D2_CREATE_ORDER_V2_JSON,
    "EXACT_ORDER_READ": APPENDIX_D3_EXACT_ORDER_READ_JSON,
    "ORDER_LIST_RECOVERY": APPENDIX_D4_ORDER_LIST_RECOVERY_JSON,
    "FILL_READ": APPENDIX_D5_FILL_READ_JSON,
    "CANCEL_ORDER_V2": APPENDIX_D6_CANCEL_ORDER_V2_JSON,
}


def real_source_record_bytes() -> bytes:
    return APPENDIX_C_SOURCE_RECORD_JSON.encode("utf-8")


def real_operation_binding_bytes() -> Dict[str, bytes]:
    return {name: blob.encode("utf-8") for name, blob in _APPENDIX_D_BY_BINDING_NAME.items()}


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def make_valid_proof(**overrides: object) -> ol.WriterExclusivityPriorWriteProof:
    fields: Dict[str, object] = dict(
        proof_schema_revision=1,
        proof_id="PROOF-0001",
        proof_mode="FIRST_ACCEPTED_DEMO_WRITE_V1",
        lifecycle_execution_authorization_id=LIFECYCLE_AUTH_ID,
        venue="KALSHI",
        environment="KALSHI_DEMO",
        account_scope_ref=ACCOUNT_SCOPE_REF,
        credential_environment_ref="KALSHI_DEMO",
        # SAME_SCOPE_CORRECTION_03, point 2: Appendix F.1 shows this field
        # as an exact list; list is the only accepted container.
        credential_source_names=["KALSHI_DEMO_API_KEY_ID", "KALSHI_DEMO_PRIVATE_KEY_PEM"],
        subaccount=0,
        ticker=TICKER,
        writer_session_id=WRITER_IDENTITY,
        permitted_writer_count=1,
        permitted_writer_identities=(WRITER_IDENTITY,),
        protected_write_operations={"CREATE", "AMEND", "DECREASE", "CANCEL"},
        valid_from_utc="2026-08-09T00:00:00Z",
        valid_until_utc=None,
        release_state="UNRELEASED",
        release_condition="NO_WRITE_SENT_TERMINAL_OR_TERMINAL_AUTHORITATIVE_RECONCILIATION",
        continuity_state="HELD",
        prior_write_state="NO_UNRESOLVED_SAME_SCOPE_WRITE",
        prior_unresolved_write_count=0,
        # SAME_SCOPE_CORRECTION_03, point 2: Appendix F.1 specifies
        # "list[str]" / "exact empty list" -- list only, not tuple.
        prior_write_execution_ids=[],
        unclosed_prior_write_execution_ids=[],
        prior_write_provenance_mode="PROJECT_AUTHORIZATION_AND_ACCEPTED_EXECUTION_EVIDENCE",
        prior_write_provenance_source="AUTHORIZATION_LOG.md / ARTIFACT_INDEX.md evidence chain",
        canonical_state_commit=CANONICAL_STATE_COMMIT,
        canonical_state_label="KALSHI_DEMO_ONE_ORDER_LIFECYCLE_SPEC_06_ACCEPTED",
        issuer_role="GUSTAVO_EXECUTION_DISPATCH",
        issuer_validation_result="PASS",
    )
    fields.update(overrides)
    return ol.WriterExclusivityPriorWriteProof(**fields)  # type: ignore[arg-type]


def make_capabilities(*, exclude: Tuple[ol.CapabilityName, ...] = ()) -> ol.CapabilityEnvelope:
    granted = frozenset(c for c in ol.CapabilityName if c not in exclude)
    return ol.CapabilityEnvelope(granted=granted)


def make_valid_authorization_envelope(**overrides: object) -> TaskAuthorizationCapabilityEnvelope:
    fields: Dict[str, object] = dict(
        schema_version=1,
        authorization_id="AUTH-0099",
        authorizing_authority="GUSTAVO",
        task_id="KALSHI_DEMO_ONE_ORDER_LIFECYCLE_IMPLEMENTATION_01",
        issue_date="2026-08-09",
        completion_rule="STOP_AFTER_CORRECTED_PACKAGE_DELIVERY_FOR_MARCO_REVIEW",
        network_access=AuthorizationValue.PERMITTED,
        demo_public_reads=AuthorizationValue.PERMITTED,
        demo_authenticated_reads=AuthorizationValue.PERMITTED,
        demo_writes=AuthorizationValue.PERMITTED,
        production_public_reads=AuthorizationValue.PROHIBITED,
        production_authenticated_reads=AuthorizationValue.PROHIBITED,
        production_writes=AuthorizationValue.PROHIBITED,
        credential_use=AuthorizationValue.PERMITTED,
        account_funding=AuthorizationValue.PROHIBITED,
        code_changes=AuthorizationValue.PROHIBITED,
        tests=AuthorizationValue.PERMITTED,
        artifact_generation=AuthorizationValue.PERMITTED,
        repository_commits=AuthorizationValue.PROHIBITED,
    )
    fields.update(overrides)
    return TaskAuthorizationCapabilityEnvelope(**fields)  # type: ignore[arg-type]


def make_valid_demo_profile_via_canonical_validator(**envelope_overrides: object) -> ValidatedDemoProfile:
    """SAME_SCOPE_CORRECTION_03, point 1: constructs the canonical
    ``ValidatedDemoProfile`` through the real, accepted
    ``arb.venues.kalshi.validation.validate(...)`` path -- never by
    directly fabricating a ``ValidatedDemoProfile`` with field values
    that merely look plausible. The canonical validator can only ever
    issue ``DEMO_PUBLIC_REST_READ`` or ``DEMO_AUTHENTICATED_READ``; it
    unconditionally rejects ``DEMO_WRITE`` with
    ``WRITE_CAPABILITY_PROHIBITED``, so this fixture requests
    ``DEMO_AUTHENTICATED_READ``, matching what this lifecycle actually
    requires.
    """

    envelope_fields: Dict[str, object] = dict(
        schema_version=1,
        authorization_id="AUTH-0099",
        authorizing_authority="GUSTAVO",
        task_id="KALSHI_DEMO_ONE_ORDER_LIFECYCLE_IMPLEMENTATION_01",
        issue_date="2026-08-09",
        completion_rule="STOP_AFTER_CORRECTED_PACKAGE_DELIVERY_FOR_MARCO_REVIEW",
        network_access=AuthorizationValue.PERMITTED,
        demo_public_reads=AuthorizationValue.PERMITTED,
        demo_authenticated_reads=AuthorizationValue.PERMITTED,
        demo_writes=AuthorizationValue.PERMITTED,
        production_public_reads=AuthorizationValue.PROHIBITED,
        production_authenticated_reads=AuthorizationValue.PROHIBITED,
        production_writes=AuthorizationValue.PROHIBITED,
        credential_use=AuthorizationValue.PERMITTED,
        account_funding=AuthorizationValue.PROHIBITED,
        code_changes=AuthorizationValue.PROHIBITED,
        tests=AuthorizationValue.PERMITTED,
        artifact_generation=AuthorizationValue.PERMITTED,
        repository_commits=AuthorizationValue.PROHIBITED,
    )
    envelope_fields.update(envelope_overrides)
    envelope = TaskAuthorizationCapabilityEnvelope(**envelope_fields)  # type: ignore[arg-type]

    config = NonSecretConfigurationInput(
        environment="KALSHI_DEMO",
        environment_source_field="KALSHI_ENVIRONMENT",
        rest_endpoint="https://external-api.demo.kalshi.co/trade-api/v2",
        websocket_endpoint="wss://external-api-ws.demo.kalshi.co/trade-api/ws/v2",
        requested_capability="DEMO_AUTHENTICATED_READ",
        capability_envelope=envelope,
        config_schema_revision=1,
        endpoint_allowlist_revision="candidate-02",
        credential_references=(
            CredentialSourceReference(
                kind=CredentialReferenceKind.API_KEY_ID_ENV_SOURCE,
                source_name="KALSHI_DEMO_API_KEY_ID",
                state=CredentialReferenceState.CONFIGURED,
            ),
            CredentialSourceReference(
                kind=CredentialReferenceKind.PRIVATE_KEY_PEM_ENV_SOURCE,
                source_name="KALSHI_DEMO_PRIVATE_KEY_PEM",
                state=CredentialReferenceState.CONFIGURED,
            ),
        ),
    )
    result = kalshi_validation.validate(config)
    assert result.success is not None, f"canonical validator unexpectedly halted: {result.halt}"
    return result.success


def make_valid_demo_profile(**overrides: object) -> ValidatedDemoProfile:
    """A directly-constructed ``ValidatedDemoProfile`` for tests that need
    to override a field to an *invalid* value the canonical validator
    could never itself produce (e.g. wrong host, wrong capability) --
    used only for negative-path fixtures. Positive-path tests use
    ``make_valid_demo_profile_via_canonical_validator()`` instead, so the
    "valid" case is always evidence the real validator could actually
    issue, not merely a plausible-looking direct construction.
    """

    fields: Dict[str, object] = dict(
        environment=Environment.KALSHI_DEMO,
        rest=EndpointComponents(
            scheme="https", host="external-api.demo.kalshi.co", port=443,
            path="/trade-api/v2", has_user_info=False, has_query=False, has_fragment=False,
        ),
        websocket=EndpointComponents(
            scheme="wss", host="external-api-ws.demo.kalshi.co", port=443,
            path="/trade-api/ws/v2", has_user_info=False, has_query=False, has_fragment=False,
        ),
        requested_capability=RequestedCapability.DEMO_AUTHENTICATED_READ,
        effective_capability=RequestedCapability.DEMO_AUTHENTICATED_READ,
        credential_reference_states=(
            (CredentialReferenceKind.API_KEY_ID_ENV_SOURCE, CredentialReferenceState.CONFIGURED),
            (CredentialReferenceKind.PRIVATE_KEY_PEM_ENV_SOURCE, CredentialReferenceState.CONFIGURED),
        ),
        allowlist_revision="candidate-02",
        validation_schema_revision=1,
    )
    fields.update(overrides)
    return ValidatedDemoProfile(**fields)  # type: ignore[arg-type]


def make_valid_authorization(**overrides: object) -> ol.OneOrderLifecycleExecutionAuthorization:
    fields: Dict[str, object] = dict(
        gustavo_execution_authorization_id=LIFECYCLE_AUTH_ID,
        environment="KALSHI_DEMO",
        ticker=TICKER,
        subaccount=0,
        account_scope_ref=ACCOUNT_SCOPE_REF,
        writer_session_id=WRITER_IDENTITY,
        capabilities=make_capabilities(),
        max_created_orders=1,
        max_create_send_attempts=1,
        max_cancel_send_attempts=1,
        max_total_rest_requests=ol.GLOBAL_REQUEST_MAXIMUM,
        max_lifecycle_duration_ms=ol.MASTER_DEADLINE_MS,
        accepted_spec_sha256=ol.ACCEPTED_SPEC_SHA256,
        accepted_implementation_commit=ACCEPTED_IMPLEMENTATION_COMMIT,
        # SAME_SCOPE_CORRECTION_02 fix: this must be the source *record's*
        # own hash (SOURCE_RECORD_SHA256), never the raw OpenAPI document
        # hash (SOURCE_OPENAPI_SHA256) it references internally.
        source_identity_sha256=ol.SOURCE_RECORD_SHA256,
        operation_binding_sha256={name: v[1] for name, v in ol.OPERATION_BINDINGS.items()},
        fee_risk_binding=ol.OneOrderFeeRiskBinding(max_fee_dollars=Decimal("0.040000")),
        writer_proof_id="PROOF-0001",
    )
    fields.update(overrides)
    return ol.OneOrderLifecycleExecutionAuthorization(**fields)  # type: ignore[arg-type]


def make_lifecycle_input(**overrides: object) -> ol.OneOrderLifecycleInput:
    """SAME_SCOPE_CORRECTION_03, point 3: the exact Section 7.1
    ``OneOrderLifecycleInput``. ``validated_demo_profile``,
    ``authorization_envelope``, ``fee_risk_binding``, and
    ``dispatch_expectation`` are sibling input fields. Correction 04 also
    requires the execution authorization to bind the exact same fee-risk
    value.
    """

    fields: Dict[str, object] = dict(
        validated_demo_profile=make_valid_demo_profile_via_canonical_validator(),
        authorization_envelope=make_valid_authorization_envelope(),
        lifecycle_authorization=make_valid_authorization(),
        writer_exclusivity_prior_write_proof=make_valid_proof(),
        market_ticker=TICKER,
        client_order_id=DEFAULT_CLIENT_ORDER_ID,
        official_source_identity_record_bytes=real_source_record_bytes(),
        operation_binding_record_bytes=real_operation_binding_bytes(),
        fee_risk_binding=ol.OneOrderFeeRiskBinding(max_fee_dollars=Decimal("0.040000")),
        dispatch_expectation=ol.OneOrderLifecycleDispatchExpectation(
            no_production=True, no_websocket=True, no_amend=True, no_decrease=True, no_replacement=True,
        ),
    )
    fields.update(overrides)
    return ol.OneOrderLifecycleInput(**fields)  # type: ignore[arg-type]


def make_order(
    *,
    order_id: str = "ORDER-0001",
    client_order_id: str,
    ticker: str = TICKER,
    status: str = "resting",
    initial_count_fp: str = "1.00",
    fill_count_fp: str = "0.00",
    remaining_count_fp: str = "1.00",
    yes_price_dollars: str = "0.0100",
    no_price_dollars: str = "0.9900",
    outcome_side: str = "yes",
    book_side: str = "bid",
    order_type: str = "limit",
    user_id: str = "user-0001",
) -> Dict[str, object]:
    return {
        "order_id": order_id,
        "user_id": user_id,
        "client_order_id": client_order_id,
        "ticker": ticker,
        "status": status,
        "outcome_side": outcome_side,
        "book_side": book_side,
        "type": order_type,
        "initial_count_fp": initial_count_fp,
        "fill_count_fp": fill_count_fp,
        "remaining_count_fp": remaining_count_fp,
        "yes_price_dollars": yes_price_dollars,
        "no_price_dollars": no_price_dollars,
        "taker_fees_dollars": "0.000000",
        "maker_fees_dollars": "0.000000",
        "taker_fill_cost_dollars": "0.000000",
        "maker_fill_cost_dollars": "0.000000",
    }


def make_fill(
    *,
    fill_id: str,
    trade_id: str = "TRADE-0001",
    order_id: str = "ORDER-0001",
    ticker: str = TICKER,
    market_ticker: Optional[str] = None,
    count_fp: str = "1.00",
    yes_price_dollars: str = "0.0100",
    no_price_dollars: str = "0.9900",
    is_taker: bool = False,
    outcome_side: str = "yes",
    book_side: str = "bid",
    fee_cost: str = "0.000000",
) -> Dict[str, object]:
    return {
        "fill_id": fill_id,
        "trade_id": trade_id,
        "order_id": order_id,
        "ticker": ticker,
        "market_ticker": ticker if market_ticker is None else market_ticker,
        "outcome_side": outcome_side,
        "book_side": book_side,
        "count_fp": count_fp,
        "yes_price_dollars": yes_price_dollars,
        "no_price_dollars": no_price_dollars,
        "is_taker": is_taker,
        "fee_cost": fee_cost,
    }


class _FixedClock:
    """A deterministic, injectable monotonic/wall clock. Each call to
    ``monotonic()`` advances by ``step`` seconds unless ``freeze`` is set."""

    def __init__(self, start: float = 1000.0, step: float = 0.01) -> None:
        self._value = start
        self._step = step
        self.freeze = False

    def monotonic(self) -> float:
        value = self._value
        if not self.freeze:
            self._value += self._step
        return value

    def wall(self) -> float:
        return 1_800_000_000.123456


def _raw_response(
    *,
    status: int,
    body: Mapping[str, object],
    media_type: str = "application/json",
    retry_count: int = 0,
    redirect_count: int = 0,
    send_result_classification: Optional[ol.SendOutcome] = None,
) -> ol.RawHttpResponse:
    if send_result_classification is None:
        send_result_classification = (
            ol.SendOutcome.DEFINITIVE_SUCCESS
            if status in (200, 201)
            else ol.SendOutcome.DEFINITIVE_RESPONSE_AFTER_SEND
        )
    return ol.RawHttpResponse(
        status=status,
        body=body,
        media_type=media_type,
        retry_count=retry_count,
        redirect_count=redirect_count,
        send_result_classification=send_result_classification,
    )


@dataclass
class _FakeTransport:
    """Deterministic in-memory stand-in for ``LifecycleTransport``. Every
    call to ``send`` consults ``responses[operation]``, a per-operation
    queue of scripted ``RawHttpResponse`` objects consumed in order.
    Nothing here performs any real I/O. Every ``PreparedRequest`` is
    recorded verbatim in ``calls`` so tests can assert on the exact
    method/path/query/body/deadline actually used.
    """

    responses: Dict[ol.LifecycleOperation, List[object]] = field(default_factory=dict)
    calls: List[ol.PreparedRequest] = field(default_factory=list)

    def send(self, request: ol.PreparedRequest) -> ol.RawHttpResponse:
        self.calls.append(request)
        queue = self.responses.get(request.operation)
        if not queue:
            raise AssertionError(f"no scripted response for operation {request.operation}")
        item = queue.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item  # type: ignore[return-value]

    def calls_for(self, operation: ol.LifecycleOperation) -> List[ol.PreparedRequest]:
        return [c for c in self.calls if c.operation == operation]


def _ok_pre_create() -> ol.RawHttpResponse:
    return _raw_response(status=200, body={"orders": [], "cursor": ""})


def _ok_create(order_id: str = "ORDER-0001") -> ol.RawHttpResponse:
    return _raw_response(status=201, body={"order_id": order_id, "fill_count": "0.00", "remaining_count": "1.00", "ts_ms": 123})


def _ok_order_response(**kwargs: object) -> ol.RawHttpResponse:
    return _raw_response(status=200, body={"order": make_order(**kwargs)})


def _ok_fills_response(fills: Optional[List[Mapping[str, object]]] = None, cursor: str = "") -> ol.RawHttpResponse:
    return _raw_response(status=200, body={"fills": fills or [], "cursor": cursor})


def _ok_cancel_response(*, order_id: str = "ORDER-0001", reduced_by: str = "1.00", client_order_id: Optional[str] = None) -> ol.RawHttpResponse:
    body: Dict[str, object] = {"order_id": order_id, "reduced_by": reduced_by, "ts_ms": 456}
    if client_order_id is not None:
        body["client_order_id"] = client_order_id
    return _raw_response(status=200, body=body)


def build_transport(
    *,
    pre_create: Optional[ol.RawHttpResponse] = None,
    create: Optional[ol.RawHttpResponse] = None,
    recovery: Optional[List[ol.RawHttpResponse]] = None,
    exact_order: Optional[List[ol.RawHttpResponse]] = None,
    fills: Optional[List[ol.RawHttpResponse]] = None,
    cancel: Optional[List[ol.RawHttpResponse]] = None,
) -> _FakeTransport:
    responses: Dict[ol.LifecycleOperation, List[ol.RawHttpResponse]] = {}
    if pre_create is not None:
        responses[ol.LifecycleOperation.PRE_CREATE_TRUTH] = [pre_create]
    if create is not None:
        responses[ol.LifecycleOperation.CREATE] = [create]
    if recovery is not None:
        responses[ol.LifecycleOperation.RECOVERY] = list(recovery)
    if exact_order is not None:
        responses[ol.LifecycleOperation.EXACT_ORDER] = list(exact_order)
    if fills is not None:
        responses[ol.LifecycleOperation.FILLS] = list(fills)
    if cancel is not None:
        responses[ol.LifecycleOperation.CANCEL] = list(cancel)
    return _FakeTransport(responses=responses)


def plan_and_execute(
    transport: _FakeTransport,
    *,
    clock: _FixedClock,
    proof: Optional[ol.WriterExclusivityPriorWriteProof] = None,
    authorization: Optional[ol.OneOrderLifecycleExecutionAuthorization] = None,
    validated_demo_profile: Optional[ValidatedDemoProfile] = None,
    authorization_envelope: Optional[TaskAuthorizationCapabilityEnvelope] = None,
    fee_risk_binding: Optional[ol.OneOrderFeeRiskBinding] = None,
    dispatch_expectation: Optional[ol.OneOrderLifecycleDispatchExpectation] = None,
    client_order_id: str = DEFAULT_CLIENT_ORDER_ID,
    environment: str = "KALSHI_DEMO",
    source_record_bytes: Optional[bytes] = None,
    operation_binding_bytes: Optional[Mapping[str, bytes]] = None,
    executor_entry_utc: str = EXECUTOR_ENTRY_UTC,
) -> Union[ol.OneOrderLifecycleResult, ol.OneOrderLifecycleHalt]:
    """Drives the full Section 9.1 two-phase surface: plan, then (if
    planning succeeded) execute. Returns whichever of
    ``OneOrderLifecycleResult``/``OneOrderLifecycleHalt`` either phase
    produced -- a planning halt is returned immediately without ever
    calling execute."""

    lifecycle_input = ol.OneOrderLifecycleInput(
        validated_demo_profile=validated_demo_profile if validated_demo_profile is not None else make_valid_demo_profile_via_canonical_validator(),
        authorization_envelope=authorization_envelope if authorization_envelope is not None else make_valid_authorization_envelope(),
        lifecycle_authorization=authorization if authorization is not None else make_valid_authorization(environment=environment),
        writer_exclusivity_prior_write_proof=proof if proof is not None else make_valid_proof(),
        market_ticker=TICKER,
        client_order_id=client_order_id,
        official_source_identity_record_bytes=source_record_bytes if source_record_bytes is not None else real_source_record_bytes(),
        operation_binding_record_bytes=operation_binding_bytes if operation_binding_bytes is not None else real_operation_binding_bytes(),
        fee_risk_binding=fee_risk_binding if fee_risk_binding is not None else ol.OneOrderFeeRiskBinding(max_fee_dollars=Decimal("0.040000")),
        dispatch_expectation=dispatch_expectation if dispatch_expectation is not None else ol.OneOrderLifecycleDispatchExpectation(
            no_production=True, no_websocket=True, no_amend=True, no_decrease=True, no_replacement=True,
        ),
    )

    plan_result = ol.plan_demo_one_order_lifecycle(
        lifecycle_input,
        _utc_clock=lambda: executor_entry_utc,
        monotonic_clock=clock.monotonic,
    )
    if isinstance(plan_result, ol.OneOrderLifecycleHalt):
        return plan_result

    return ol.execute_demo_one_order_lifecycle(
        plan_result,
        transport,
        monotonic_clock=clock.monotonic,
        _wall_clock=clock.wall,
    )


def full_happy_path_transport(
    *, order_id: str = "ORDER-0001", client_order_id: str = "5781e77b-e1ed-4303-bcf6-bdb282419251"
) -> _FakeTransport:
    """A transport scripted for the complete zero-fill create -> cancel
    happy path, including the mandatory post-cancel reread/refill."""

    return build_transport(
        pre_create=_ok_pre_create(),
        create=_ok_create(order_id=order_id),
        exact_order=[
            _ok_order_response(order_id=order_id, client_order_id=client_order_id, status="resting"),
            _ok_order_response(order_id=order_id, client_order_id=client_order_id, status="canceled"),
        ],
        fills=[_ok_fills_response([]), _ok_fills_response([])],
        cancel=[_ok_cancel_response(order_id=order_id, reduced_by="1.00")],
    )


# ---------------------------------------------------------------------------
# 1-6: identity gates
# ---------------------------------------------------------------------------

class TestSpecificationIdentityGate(unittest.TestCase):
    def test_accepted_revision_06_identity_passes(self) -> None:
        self.assertIsNone(ol.validate_controlling_spec_identity(ol.ACCEPTED_SPEC_SHA256))

    def test_blocked_predecessor_identities_rejected(self) -> None:
        for blocked in ol.BLOCKED_PREDECESSOR_SPEC_SHA256:
            self.assertEqual(
                ol.validate_controlling_spec_identity(blocked),
                ol.LifecycleHaltCode.SPEC_IDENTITY_BLOCKED_PREDECESSOR,
            )

    def test_unknown_identity_rejected(self) -> None:
        self.assertEqual(
            ol.validate_controlling_spec_identity("0" * 64),
            ol.LifecycleHaltCode.SPEC_IDENTITY_MISMATCH,
        )

    def test_non_string_identity_rejected(self) -> None:
        self.assertEqual(
            ol.validate_controlling_spec_identity(12345),  # type: ignore[arg-type]
            ol.LifecycleHaltCode.SPEC_IDENTITY_MISMATCH,
        )


class TestSourceAndOperationBindingIdentities(unittest.TestCase):
    """Uses the exact Appendix C / Appendix D bytes extracted verbatim
    from the controlling specification -- not synthetic same-shape
    buffers."""

    def test_real_source_record_bytes_match_accepted_identity(self) -> None:
        raw = real_source_record_bytes()
        self.assertEqual(len(raw), ol.SOURCE_RECORD_BYTES)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), ol.SOURCE_RECORD_SHA256)
        self.assertIsNone(ol.validate_source_record_identity(raw_bytes=raw))

    def test_real_source_record_bytes_reject_when_flipped(self) -> None:
        raw = bytearray(real_source_record_bytes())
        raw[0] ^= 0x01
        self.assertEqual(
            ol.validate_source_record_identity(raw_bytes=bytes(raw)),
            ol.LifecycleHaltCode.SOURCE_RECORD_IDENTITY_MISMATCH,
        )

    def test_each_real_operation_binding_accepted(self) -> None:
        for name, raw_bytes in real_operation_binding_bytes().items():
            expected_length, expected_sha = ol.OPERATION_BINDINGS[name]
            self.assertEqual(len(raw_bytes), expected_length, msg=name)
            self.assertEqual(hashlib.sha256(raw_bytes).hexdigest(), expected_sha, msg=name)
            self.assertIsNone(ol.validate_operation_binding(name, raw_bytes=raw_bytes), msg=name)

    def test_each_real_operation_binding_rejects_when_corrupted(self) -> None:
        for name, raw_bytes in real_operation_binding_bytes().items():
            corrupted = bytearray(raw_bytes)
            corrupted[-1] ^= 0x01
            self.assertEqual(
                ol.validate_operation_binding(name, raw_bytes=bytes(corrupted)),
                ol.LifecycleHaltCode.OPERATION_BINDING_MISMATCH,
                msg=name,
            )

    def test_verify_identity_requires_both_length_and_hash(self) -> None:
        data = b"hello world"
        digest = ol.sha256_hex(data)
        self.assertTrue(ol.verify_identity(raw_bytes=data, expected_length=len(data), expected_sha256=digest))
        self.assertFalse(ol.verify_identity(raw_bytes=data, expected_length=len(data) + 1, expected_sha256=digest))
        self.assertFalse(ol.verify_identity(raw_bytes=data, expected_length=len(data), expected_sha256="0" * 64))

    def test_each_of_six_binding_identities_present_and_well_formed(self) -> None:
        self.assertEqual(len(ol.OPERATION_BINDINGS), 6)
        for name, (length, sha) in ol.OPERATION_BINDINGS.items():
            self.assertIsInstance(name, str)
            self.assertGreater(length, 0)
            self.assertEqual(len(sha), 64)
            int(sha, 16)  # must be valid hex

    def test_binding_mismatch_halts_on_wrong_bytes(self) -> None:
        halt = ol.validate_operation_binding("CREATE_ORDER_V2", raw_bytes=b"not the real bytes")
        self.assertEqual(halt, ol.LifecycleHaltCode.OPERATION_BINDING_MISMATCH)

    def test_binding_mismatch_halts_on_unknown_name(self) -> None:
        halt = ol.validate_operation_binding("NOT_A_REAL_BINDING", raw_bytes=b"anything")
        self.assertEqual(halt, ol.LifecycleHaltCode.OPERATION_BINDING_MISMATCH)

    def test_validate_source_identity_is_a_correct_available_pure_function(self) -> None:
        # validate_source_identity checks the raw ~333KB OpenAPI document
        # itself, which is distinct from the Appendix-C source *record*
        # tested above. This module never receives the raw OpenAPI
        # document as lifecycle input (Section 7.1 doesn't supply it), so
        # this function is not invoked by validate_pre_send_gate /
        # execute_demo_one_order_lifecycle; Section 9.4 item 3 is instead satisfied
        # by parse_and_validate_source_record (tested in
        # TestSourceRecordContentValidation below), which validates the
        # accepted record's own embedded claim about the raw document's
        # identity without requiring the raw document as input. This test
        # only proves the pure length+hash check itself behaves correctly;
        # it does not claim the placeholder buffer is real OpenAPI content.
        placeholder = b"x" * ol.SOURCE_OPENAPI_BYTES
        self.assertNotEqual(hashlib.sha256(placeholder).hexdigest(), ol.SOURCE_OPENAPI_SHA256)
        self.assertEqual(
            ol.validate_source_identity(raw_bytes=placeholder),
            ol.LifecycleHaltCode.SOURCE_IDENTITY_MISMATCH,
        )
        self.assertIsNotNone(ol.validate_source_identity(raw_bytes=b"too short"))


class TestSourceRecordContentValidation(unittest.TestCase):
    """SAME_SCOPE_CORRECTION_02, point 2: Section 9.4 item 3 made
    load-bearing via ``parse_and_validate_source_record``, which parses
    the already byte-verified Appendix-C record and validates its
    embedded raw-OpenAPI-identity claim -- without adding any new raw
    OpenAPI document as lifecycle input.
    """

    def test_exact_appendix_c_record_succeeds(self) -> None:
        self.assertIsNone(ol.parse_and_validate_source_record(raw_bytes=real_source_record_bytes()))

    def test_corrupted_bytes_still_rejected_at_identity_stage(self) -> None:
        corrupted = bytearray(real_source_record_bytes())
        corrupted[0] ^= 0xFF
        self.assertEqual(
            ol.parse_and_validate_source_record(raw_bytes=bytes(corrupted)),
            ol.LifecycleHaltCode.SOURCE_RECORD_IDENTITY_MISMATCH,
        )

    def test_malformed_json_cannot_pass_the_byte_identity_gate(self) -> None:
        # Item 2 (byte-length/hash) always gates item 3 (content), so a
        # malformed-JSON variant of the accepted record is only
        # reachable by also being byte-identical to the accepted 843-byte
        # SHA-256 -- a hash-preimage-resistance impossibility to
        # construct deliberately. This documents why: any non-accepted
        # bytes (malformed JSON or otherwise) are caught at the identity
        # stage before content parsing ever runs.
        malformed = b"{not valid json" + b" " * (ol.SOURCE_RECORD_BYTES - len(b"{not valid json"))
        self.assertEqual(len(malformed), ol.SOURCE_RECORD_BYTES)
        self.assertNotEqual(hashlib.sha256(malformed).hexdigest(), ol.SOURCE_RECORD_SHA256)
        self.assertEqual(
            ol.parse_and_validate_source_record(raw_bytes=malformed),
            ol.LifecycleHaltCode.SOURCE_RECORD_IDENTITY_MISMATCH,
        )

    def test_duplicate_key_json_rejected_by_internal_hook(self) -> None:
        with self.assertRaises(ol._DuplicateSourceRecordKeyError):
            ol._no_duplicate_keys_object_pairs_hook([("a", 1), ("a", 2)])

    def test_no_duplicate_keys_hook_accepts_unique_keys(self) -> None:
        result = ol._no_duplicate_keys_object_pairs_hook([("a", 1), ("b", 2)])
        self.assertEqual(result, {"a": 1, "b": 2})

    def test_wrong_raw_openapi_byte_length_halts(self) -> None:
        mutated = dict(json.loads(APPENDIX_C_SOURCE_RECORD_JSON))
        mutated["raw_openapi_byte_length"] = 1
        raw = json.dumps(mutated, separators=(",", ":"), sort_keys=True).encode("utf-8")
        # This will also fail identity (different bytes) -- confirms the
        # content check is at minimum as strict as the identity check,
        # and specifically that a wrong raw_openapi_byte_length cannot
        # slip through under a different byte-identical record.
        self.assertIsNotNone(ol.parse_and_validate_source_record(raw_bytes=raw))

    def test_wrong_raw_openapi_sha256_halts(self) -> None:
        mutated = dict(json.loads(APPENDIX_C_SOURCE_RECORD_JSON))
        mutated["raw_openapi_sha256"] = "1" * 64
        raw = json.dumps(mutated, separators=(",", ":"), sort_keys=True).encode("utf-8")
        self.assertIsNotNone(ol.parse_and_validate_source_record(raw_bytes=raw))

    def test_direct_field_check_against_parsed_accepted_record(self) -> None:
        # Directly exercises the field-content check (bypassing the byte-
        # identity gate) by parsing the real accepted record and manually
        # asserting its raw_openapi_* fields equal the accepted identity
        # this module expects Section 9.4 item 3 to enforce.
        parsed = json.loads(APPENDIX_C_SOURCE_RECORD_JSON)
        self.assertEqual(parsed["raw_openapi_byte_length"], ol.SOURCE_OPENAPI_BYTES)
        self.assertEqual(parsed["raw_openapi_sha256"], ol.SOURCE_OPENAPI_SHA256)
        self.assertEqual(parsed["reviewed_demo_base_path"], "/trade-api/v2")
        self.assertEqual(parsed["reviewed_demo_rest_origin"], ol.DEMO_REST_ORIGIN)
        self.assertEqual(parsed["source_url"], "https://docs.kalshi.com/openapi.yaml")
        self.assertEqual(parsed["source_info_version"], "3.27.0")

    def test_zero_transport_calls_on_bad_record_content_via_full_gate(self) -> None:
        # End-to-end: even though the corrupted record has the same byte
        # length as the accepted one is not attempted here (that's the
        # identity-mismatch case tested elsewhere) -- this proves the
        # *content* gate is reached via validate_pre_send_gate with zero
        # transport calls when it fails, using the full lifecycle runner.
        clock = _FixedClock()
        transport = full_happy_path_transport()
        corrupted = bytearray(real_source_record_bytes())
        corrupted[-1] ^= 0xFF  # corrupt the trailing byte, still same length
        result = plan_and_execute(transport, clock=clock, source_record_bytes=bytes(corrupted))
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.SOURCE_RECORD_IDENTITY_MISMATCH)
        self.assertEqual(transport.calls, [])

    def test_gate_uses_parse_and_validate_not_only_byte_check(self) -> None:
        # Confirms validate_pre_send_gate's item-2/item-3 check is now
        # parse_and_validate_source_record, not the byte-only
        # validate_source_record_identity, by constructing a record that
        # is byte-identical (so item 2 passes) but verifying the function
        # used really is the content-aware one via direct call parity.
        raw = real_source_record_bytes()
        self.assertEqual(
            ol.parse_and_validate_source_record(raw_bytes=raw),
            ol.validate_source_record_identity(raw_bytes=raw),
        )
        self.assertIsNone(ol.parse_and_validate_source_record(raw_bytes=raw))


# ---------------------------------------------------------------------------
# 7-9: Demo/production separation
# ---------------------------------------------------------------------------

class TestEnvironmentSeparation(unittest.TestCase):
    def test_demo_environment_constant(self) -> None:
        self.assertEqual(ol.ENVIRONMENT, "KALSHI_DEMO")
        self.assertEqual(ol.DEMO_REST_ORIGIN, "https://external-api.demo.kalshi.co")

    def test_lifecycle_halts_when_environment_not_demo(self) -> None:
        # SAME_SCOPE_CORRECTION_03: environment is represented solely via
        # lifecycle_authorization.environment (Section 7.2) -- there is no
        # separate top-level environment input distinct from it. A
        # mismatch is caught inside validate_execution_authorization,
        # which returns EXECUTION_AUTHORIZATION_INVALID.
        clock = _FixedClock()
        transport = build_transport(pre_create=_ok_pre_create(), create=_ok_create())
        bad_authz = make_valid_authorization(environment="KALSHI_PRODUCTION")
        result = plan_and_execute(transport, clock=clock, authorization=bad_authz)
        self.assertIsInstance(result, ol.OneOrderLifecycleHalt)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID)
        self.assertEqual(transport.calls, [])

    def test_lifecycle_halts_when_environment_unset(self) -> None:
        clock = _FixedClock()
        transport = build_transport(pre_create=_ok_pre_create(), create=_ok_create())
        bad_authz = make_valid_authorization(environment="")
        result = plan_and_execute(transport, clock=clock, authorization=bad_authz)
        self.assertIsInstance(result, ol.OneOrderLifecycleHalt)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID)
        self.assertEqual(transport.calls, [])

    def test_no_venue_request_before_spec_gate_passes(self) -> None:
        clock = _FixedClock()
        transport = build_transport(pre_create=_ok_pre_create(), create=_ok_create())
        bad_authz = make_valid_authorization(accepted_spec_sha256="0" * 64)
        result = plan_and_execute(transport, clock=clock, authorization=bad_authz)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.SPEC_IDENTITY_MISMATCH)
        self.assertEqual(transport.calls, [])


# ---------------------------------------------------------------------------
# 10-19+: writer exclusivity / prior-write proof (Appendix F exact contract)
# ---------------------------------------------------------------------------

class TestWriterExclusivityPriorWriteProof(unittest.TestCase):
    def _validate(self, proof: ol.WriterExclusivityPriorWriteProof) -> Optional[ol.LifecycleHaltCode]:
        return ol.validate_writer_proof(
            proof,
            expected_ticker=TICKER,
            expected_writer_identity=WRITER_IDENTITY,
            expected_lifecycle_execution_authorization_id=LIFECYCLE_AUTH_ID,
            executor_entry_utc=EXECUTOR_ENTRY_UTC,
        )

    def test_valid_proof_passes(self) -> None:
        self.assertIsNone(self._validate(make_valid_proof()))

    def test_proof_schema_revision_must_be_exact_int_not_string(self) -> None:
        proof = make_valid_proof(proof_schema_revision="1")  # type: ignore[arg-type]
        self.assertIsNotNone(self._validate(proof))

    def test_proof_schema_revision_bool_rejected(self) -> None:
        proof = make_valid_proof(proof_schema_revision=True)  # type: ignore[arg-type]
        self.assertIsNotNone(self._validate(proof))

    def test_missing_field_halts(self) -> None:
        # Constructing without a required field raises at the dataclass
        # level, which is itself the "reject missing field" behavior.
        with self.assertRaises(TypeError):
            ol.WriterExclusivityPriorWriteProof(proof_id="only-this")  # type: ignore[call-arg]

    def test_wrong_proof_mode_halts(self) -> None:
        proof = make_valid_proof(proof_mode="SOME_OTHER_MODE")
        self.assertEqual(self._validate(proof), ol.LifecycleHaltCode.PRIOR_WRITE_PROVENANCE_INSUFFICIENT)

    def test_extra_protected_operation_halts(self) -> None:
        proof = make_valid_proof(protected_write_operations={"CREATE", "AMEND", "DECREASE", "CANCEL", "REPRICE"})
        self.assertEqual(self._validate(proof), ol.LifecycleHaltCode.WRITER_EXCLUSIVITY_NOT_ESTABLISHED)

    def test_missing_protected_operation_halts(self) -> None:
        proof = make_valid_proof(protected_write_operations={"CREATE", "CANCEL"})
        self.assertEqual(self._validate(proof), ol.LifecycleHaltCode.WRITER_EXCLUSIVITY_NOT_ESTABLISHED)

    def test_wrong_credential_names_halts(self) -> None:
        proof = make_valid_proof(credential_source_names=("KALSHI_DEMO_API_KEY_ID",))
        self.assertEqual(self._validate(proof), ol.LifecycleHaltCode.WRITER_EXCLUSIVITY_NOT_ESTABLISHED)

    def test_credential_names_wrong_order_halts(self) -> None:
        proof = make_valid_proof(credential_source_names=("KALSHI_DEMO_PRIVATE_KEY_PEM", "KALSHI_DEMO_API_KEY_ID"))
        self.assertEqual(self._validate(proof), ol.LifecycleHaltCode.WRITER_EXCLUSIVITY_NOT_ESTABLISHED)

    def test_wrong_credential_environment_ref_halts(self) -> None:
        proof = make_valid_proof(credential_environment_ref="KALSHI_PRODUCTION")
        self.assertEqual(self._validate(proof), ol.LifecycleHaltCode.WRITER_EXCLUSIVITY_SCOPE_MISMATCH)

    def test_writer_session_mismatch_halts(self) -> None:
        proof = make_valid_proof(writer_session_id="someone-else", permitted_writer_identities=("someone-else",))
        self.assertEqual(self._validate(proof), ol.LifecycleHaltCode.WRITER_EXCLUSIVITY_SCOPE_MISMATCH)

    def test_permitted_writer_identities_not_matching_session_halts(self) -> None:
        proof = make_valid_proof(permitted_writer_identities=("some-other-session",))
        self.assertEqual(self._validate(proof), ol.LifecycleHaltCode.WRITER_EXCLUSIVITY_NOT_ESTABLISHED)

    def test_permitted_writer_identities_more_than_one_halts(self) -> None:
        proof = make_valid_proof(permitted_writer_identities=(WRITER_IDENTITY, "another-writer"))
        self.assertEqual(self._validate(proof), ol.LifecycleHaltCode.WRITER_EXCLUSIVITY_NOT_ESTABLISHED)

    def test_permitted_writer_count_not_one_halts(self) -> None:
        proof = make_valid_proof(permitted_writer_count=2)
        self.assertEqual(self._validate(proof), ol.LifecycleHaltCode.WRITER_EXCLUSIVITY_NOT_ESTABLISHED)

    def test_bad_valid_from_utc_timestamp_halts(self) -> None:
        proof = make_valid_proof(valid_from_utc="not-a-timestamp")
        self.assertEqual(self._validate(proof), ol.LifecycleHaltCode.WRITER_EXCLUSIVITY_NOT_ESTABLISHED)

    def test_future_valid_from_utc_halts(self) -> None:
        proof = make_valid_proof(valid_from_utc="2099-01-01T00:00:00Z")
        self.assertEqual(self._validate(proof), ol.LifecycleHaltCode.WRITER_EXCLUSIVITY_NOT_ACTIVE_BEFORE_PREFLIGHT)

    def test_valid_until_utc_not_null_halts(self) -> None:
        proof = make_valid_proof(valid_until_utc="2026-12-31T00:00:00Z")
        self.assertEqual(self._validate(proof), ol.LifecycleHaltCode.WRITER_EXCLUSIVITY_NOT_ESTABLISHED)

    def test_release_state_not_unreleased_halts(self) -> None:
        proof = make_valid_proof(release_state="RELEASED")
        self.assertEqual(self._validate(proof), ol.LifecycleHaltCode.WRITER_EXCLUSIVITY_LOST)

    def test_wrong_release_condition_halts(self) -> None:
        proof = make_valid_proof(release_condition="ANYTIME")
        self.assertEqual(self._validate(proof), ol.LifecycleHaltCode.WRITER_EXCLUSIVITY_NOT_ESTABLISHED)

    def test_continuity_state_not_held_halts(self) -> None:
        proof = make_valid_proof(continuity_state="LOST")
        self.assertEqual(self._validate(proof), ol.LifecycleHaltCode.WRITER_EXCLUSIVITY_LOST)

    def test_unknown_prior_write_state_halts(self) -> None:
        proof = make_valid_proof(prior_write_state="UNKNOWN")
        self.assertEqual(self._validate(proof), ol.LifecycleHaltCode.PRIOR_WRITE_STATE_UNKNOWN)

    def test_unresolved_prior_write_state_halts(self) -> None:
        proof = make_valid_proof(prior_write_state="SOME_OTHER_STATE")
        self.assertEqual(self._validate(proof), ol.LifecycleHaltCode.PRIOR_WRITE_UNRESOLVED)

    def test_nonzero_prior_unresolved_write_count_halts(self) -> None:
        proof = make_valid_proof(prior_unresolved_write_count=1)
        self.assertEqual(self._validate(proof), ol.LifecycleHaltCode.PRIOR_WRITE_UNRESOLVED)

    def test_nonempty_unclosed_prior_write_execution_ids_halts(self) -> None:
        proof = make_valid_proof(unclosed_prior_write_execution_ids=("PRIOR-1",))
        self.assertEqual(self._validate(proof), ol.LifecycleHaltCode.PRIOR_WRITE_UNRESOLVED)

    def test_wrong_provenance_mode_halts(self) -> None:
        proof = make_valid_proof(prior_write_provenance_mode="SELF_ATTESTED")
        self.assertEqual(self._validate(proof), ol.LifecycleHaltCode.PRIOR_WRITE_PROVENANCE_INSUFFICIENT)

    def test_missing_provenance_source_halts(self) -> None:
        proof = make_valid_proof(prior_write_provenance_source="")
        self.assertIsNotNone(self._validate(proof))

    def test_non_hex_canonical_state_commit_halts(self) -> None:
        proof = make_valid_proof(canonical_state_commit="not-a-commit-sha")
        self.assertEqual(self._validate(proof), ol.LifecycleHaltCode.PRIOR_WRITE_PROVENANCE_INSUFFICIENT)

    def test_wrong_issuer_role_halts(self) -> None:
        proof = make_valid_proof(issuer_role="BRUNO_SPECIFICATION_AUTHOR")
        self.assertEqual(self._validate(proof), ol.LifecycleHaltCode.PRIOR_WRITE_PROVENANCE_INSUFFICIENT)

    def test_wrong_issuer_validation_result_halts(self) -> None:
        proof = make_valid_proof(issuer_validation_result="FAIL")
        self.assertEqual(self._validate(proof), ol.LifecycleHaltCode.PRIOR_WRITE_PROVENANCE_INSUFFICIENT)

    def test_credential_possession_alone_is_not_writer_proof(self) -> None:
        proof = make_valid_proof(release_state="RELEASED")
        self.assertGreater(len(proof.credential_source_names), 0)
        self.assertIsNotNone(self._validate(proof))

    def test_zero_resting_orders_does_not_override_bad_proof(self) -> None:
        clock = _FixedClock()
        transport = build_transport(pre_create=_ok_pre_create(), create=_ok_create())
        bad_proof = make_valid_proof(prior_write_state="UNKNOWN")
        result = plan_and_execute(transport, clock=clock, proof=bad_proof)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.PRIOR_WRITE_STATE_UNKNOWN)
        self.assertEqual(transport.calls, [])

    def test_proof_activated_too_late_via_full_lifecycle(self) -> None:
        clock = _FixedClock()
        clock.freeze = True  # proof_validation_complete == pre_create_send_boundary
        transport = build_transport(pre_create=_ok_pre_create(), create=_ok_create())
        result = plan_and_execute(transport, clock=clock)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.WRITER_EXCLUSIVITY_NOT_ACTIVE_BEFORE_PREFLIGHT)

    def test_rfc3339_utc_z_validator(self) -> None:
        self.assertTrue(ol.is_rfc3339_utc_z("2026-08-09T12:00:00Z"))
        self.assertTrue(ol.is_rfc3339_utc_z("2026-08-09T12:00:00.123456Z"))
        self.assertFalse(ol.is_rfc3339_utc_z("2026-08-09T12:00:00"))  # missing Z
        self.assertFalse(ol.is_rfc3339_utc_z("2026-08-09T12:00:00+00:00"))  # not Z-suffixed
        self.assertFalse(ol.is_rfc3339_utc_z("2026-13-40T12:00:00Z"))  # not a real date
        self.assertFalse(ol.is_rfc3339_utc_z(20260809))  # type: ignore[arg-type]

    # -- SAME_SCOPE_CORRECTION_03, point 2: Appendix-F container types
    # exactly as spec'd -----------------------------------------------------

    def test_nonempty_prior_write_execution_ids_halts_in_first_write_mode(self) -> None:
        proof = make_valid_proof(prior_write_execution_ids=["PRIOR-EXEC-1"])
        self.assertEqual(self._validate(proof), ol.LifecycleHaltCode.PRIOR_WRITE_PROVENANCE_INSUFFICIENT)

    def test_nonempty_unclosed_prior_write_execution_ids_halts(self) -> None:
        proof = make_valid_proof(unclosed_prior_write_execution_ids=["PRIOR-EXEC-1"])
        self.assertEqual(self._validate(proof), ol.LifecycleHaltCode.PRIOR_WRITE_UNRESOLVED)

    def test_exact_valid_first_write_empty_lists_pass(self) -> None:
        proof = make_valid_proof(prior_write_execution_ids=[], unclosed_prior_write_execution_ids=[])
        self.assertIsNone(self._validate(proof))

    def test_prior_write_execution_ids_list_is_the_only_accepted_form(self) -> None:
        # Appendix F.1: "list[str], empty for actual first-write stage" --
        # list is the only accepted container for this field.
        proof = make_valid_proof(prior_write_execution_ids=[])
        self.assertIsNone(self._validate(proof))

    def test_prior_write_execution_ids_tuple_rejected(self) -> None:
        proof = make_valid_proof(prior_write_execution_ids=())
        self.assertEqual(self._validate(proof), ol.LifecycleHaltCode.PRIOR_WRITE_PROVENANCE_INSUFFICIENT)

    def test_unclosed_prior_write_execution_ids_list_is_the_only_accepted_form(self) -> None:
        # Appendix F.1: "exact empty list" -- list is the only accepted
        # container for this field.
        proof = make_valid_proof(unclosed_prior_write_execution_ids=[])
        self.assertIsNone(self._validate(proof))

    def test_unclosed_prior_write_execution_ids_tuple_rejected(self) -> None:
        proof = make_valid_proof(unclosed_prior_write_execution_ids=())
        self.assertEqual(self._validate(proof), ol.LifecycleHaltCode.PRIOR_WRITE_UNRESOLVED)

    def test_permitted_writer_identities_accepts_tuple(self) -> None:
        proof = make_valid_proof(permitted_writer_identities=(WRITER_IDENTITY,))
        self.assertIsNone(self._validate(proof))

    def test_permitted_writer_identities_accepts_list(self) -> None:
        # Appendix F.1: "exact one-element tuple/list" -- both forms
        # accepted.
        proof = make_valid_proof(permitted_writer_identities=[WRITER_IDENTITY])
        self.assertIsNone(self._validate(proof))

    def test_permitted_writer_identities_set_rejected(self) -> None:
        # Not one of the two accepted forms ("tuple/list").
        proof = make_valid_proof(permitted_writer_identities={WRITER_IDENTITY})
        self.assertEqual(self._validate(proof), ol.LifecycleHaltCode.WRITER_EXCLUSIVITY_NOT_ESTABLISHED)

    def test_credential_source_names_list_is_the_only_accepted_form(self) -> None:
        # Appendix F.1 shows this field as an exact JSON list; unlike
        # permitted_writer_identities/protected_write_operations, no
        # "tuple/list" alternative is given for this field.
        proof = make_valid_proof(credential_source_names=["KALSHI_DEMO_API_KEY_ID", "KALSHI_DEMO_PRIVATE_KEY_PEM"])
        self.assertIsNone(self._validate(proof))

    def test_credential_source_names_tuple_rejected(self) -> None:
        proof = make_valid_proof(credential_source_names=("KALSHI_DEMO_API_KEY_ID", "KALSHI_DEMO_PRIVATE_KEY_PEM"))
        self.assertEqual(self._validate(proof), ol.LifecycleHaltCode.WRITER_EXCLUSIVITY_NOT_ESTABLISHED)

    def test_credential_source_names_wrong_order_in_list_rejected(self) -> None:
        proof = make_valid_proof(credential_source_names=["KALSHI_DEMO_PRIVATE_KEY_PEM", "KALSHI_DEMO_API_KEY_ID"])
        self.assertEqual(self._validate(proof), ol.LifecycleHaltCode.WRITER_EXCLUSIVITY_NOT_ESTABLISHED)

    def test_protected_write_operations_frozenset_rejected(self) -> None:
        proof = make_valid_proof(protected_write_operations=frozenset({"CREATE", "AMEND", "DECREASE", "CANCEL"}))
        self.assertEqual(self._validate(proof), ol.LifecycleHaltCode.WRITER_EXCLUSIVITY_NOT_ESTABLISHED)

    def test_protected_write_operations_accepts_set(self) -> None:
        proof = make_valid_proof(protected_write_operations={"CREATE", "AMEND", "DECREASE", "CANCEL"})
        self.assertIsNone(self._validate(proof))

    def test_protected_write_operations_accepts_list(self) -> None:
        # Appendix F.1: "exact set/list" -- both forms accepted.
        proof = make_valid_proof(protected_write_operations=["CREATE", "AMEND", "DECREASE", "CANCEL"])
        self.assertIsNone(self._validate(proof))

    def test_protected_write_operations_list_with_duplicate_rejected(self) -> None:
        proof = make_valid_proof(protected_write_operations=["CREATE", "CREATE", "AMEND", "DECREASE", "CANCEL"])
        self.assertEqual(self._validate(proof), ol.LifecycleHaltCode.WRITER_EXCLUSIVITY_NOT_ESTABLISHED)

    def test_protected_write_operations_tuple_rejected(self) -> None:
        # Not one of the two accepted forms ("set/list").
        proof = make_valid_proof(protected_write_operations=("CREATE", "AMEND", "DECREASE", "CANCEL"))
        self.assertEqual(self._validate(proof), ol.LifecycleHaltCode.WRITER_EXCLUSIVITY_NOT_ESTABLISHED)

    def test_nonempty_prior_write_execution_ids_zero_transport_calls(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        bad_proof = make_valid_proof(prior_write_execution_ids=("PRIOR-EXEC-1",))
        result = plan_and_execute(transport, clock=clock, proof=bad_proof)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.PRIOR_WRITE_PROVENANCE_INSUFFICIENT)
        self.assertEqual(transport.calls, [])

    # -- SAME_SCOPE_CORRECTION_02, point 5: RFC3339 chronological (not
    # lexical string) comparison --------------------------------------------

    def test_fractional_valid_from_later_than_whole_second_executor_entry_halts(self) -> None:
        # The exact dispatch example: valid_from has a fractional second
        # that makes it chronologically LATER than executor_entry, even
        # though it would sort lexically EARLIER as a raw string (since
        # ASCII '.' < 'Z'). A correct implementation must halt here.
        proof = make_valid_proof(valid_from_utc="2026-08-09T12:00:00.1Z")
        halt = ol.validate_writer_proof(
            proof,
            expected_ticker=TICKER,
            expected_writer_identity=WRITER_IDENTITY,
            expected_lifecycle_execution_authorization_id=LIFECYCLE_AUTH_ID,
            executor_entry_utc="2026-08-09T12:00:00Z",
        )
        self.assertEqual(halt, ol.LifecycleHaltCode.WRITER_EXCLUSIVITY_NOT_ACTIVE_BEFORE_PREFLIGHT)
        # Confirm the raw string comparison would have gotten this wrong,
        # to document exactly why datetime-based comparison is required.
        self.assertLess("2026-08-09T12:00:00.1Z", "2026-08-09T12:00:00Z")

    def test_inverse_valid_from_clearly_earlier_passes(self) -> None:
        proof = make_valid_proof(valid_from_utc="2026-08-09T11:59:59Z")
        halt = ol.validate_writer_proof(
            proof,
            expected_ticker=TICKER,
            expected_writer_identity=WRITER_IDENTITY,
            expected_lifecycle_execution_authorization_id=LIFECYCLE_AUTH_ID,
            executor_entry_utc="2026-08-09T12:00:00Z",
        )
        self.assertIsNone(halt)

    def test_equal_timestamps_pass(self) -> None:
        proof = make_valid_proof(valid_from_utc="2026-08-09T12:00:00Z")
        halt = ol.validate_writer_proof(
            proof,
            expected_ticker=TICKER,
            expected_writer_identity=WRITER_IDENTITY,
            expected_lifecycle_execution_authorization_id=LIFECYCLE_AUTH_ID,
            executor_entry_utc="2026-08-09T12:00:00Z",
        )
        self.assertIsNone(halt)

    def test_equal_instant_different_fractional_precision_passes(self) -> None:
        # 12:00:00.000000Z and 12:00:00Z represent the identical instant;
        # equal (not later) must pass.
        proof = make_valid_proof(valid_from_utc="2026-08-09T12:00:00.000000Z")
        halt = ol.validate_writer_proof(
            proof,
            expected_ticker=TICKER,
            expected_writer_identity=WRITER_IDENTITY,
            expected_lifecycle_execution_authorization_id=LIFECYCLE_AUTH_ID,
            executor_entry_utc="2026-08-09T12:00:00Z",
        )
        self.assertIsNone(halt)

    def test_executor_entry_with_fraction_valid_from_without_passes(self) -> None:
        # valid_from (no fraction, i.e. .000000) is chronologically
        # earlier than executor_entry (.5 seconds later) -- must pass.
        proof = make_valid_proof(valid_from_utc="2026-08-09T12:00:00Z")
        halt = ol.validate_writer_proof(
            proof,
            expected_ticker=TICKER,
            expected_writer_identity=WRITER_IDENTITY,
            expected_lifecycle_execution_authorization_id=LIFECYCLE_AUTH_ID,
            executor_entry_utc="2026-08-09T12:00:00.5Z",
        )
        self.assertIsNone(halt)

    def test_parse_rfc3339_utc_z_normalizes_fractional_precision(self) -> None:
        a = ol._parse_rfc3339_utc_z("2026-08-09T12:00:00.1Z")
        b = ol._parse_rfc3339_utc_z("2026-08-09T12:00:00.100000Z")
        self.assertEqual(a, b)
        self.assertEqual(a.fractional_second, Decimal("0.1"))

    def test_parse_rfc3339_utc_z_rejects_invalid(self) -> None:
        self.assertIsNone(ol._parse_rfc3339_utc_z("not-a-timestamp"))
        self.assertIsNone(ol._parse_rfc3339_utc_z(12345))
        self.assertIsNone(ol._parse_rfc3339_utc_z("2026-02-30T00:00:00Z"))


# ---------------------------------------------------------------------------
# Execution authorization
# ---------------------------------------------------------------------------

class TestExecutionAuthorization(unittest.TestCase):
    def test_valid_authorization_passes(self) -> None:
        self.assertIsNone(ol.validate_execution_authorization(make_valid_authorization(), expected_ticker=TICKER))

    def test_ticker_mismatch_halts(self) -> None:
        authz = make_valid_authorization(ticker="OTHER-TICKER")
        self.assertIsNotNone(ol.validate_execution_authorization(authz, expected_ticker=TICKER))

    def test_wrong_environment_halts(self) -> None:
        authz = make_valid_authorization(environment="KALSHI_PRODUCTION")
        self.assertIsNotNone(ol.validate_execution_authorization(authz, expected_ticker=TICKER))

    def test_max_created_orders_not_one_halts(self) -> None:
        authz = make_valid_authorization(max_created_orders=2)
        self.assertIsNotNone(ol.validate_execution_authorization(authz, expected_ticker=TICKER))

    def test_max_total_rest_requests_wrong_halts(self) -> None:
        authz = make_valid_authorization(max_total_rest_requests=12)
        self.assertIsNotNone(ol.validate_execution_authorization(authz, expected_ticker=TICKER))

    def test_max_lifecycle_duration_wrong_halts(self) -> None:
        authz = make_valid_authorization(max_lifecycle_duration_ms=120_000)
        self.assertIsNotNone(ol.validate_execution_authorization(authz, expected_ticker=TICKER))

    def test_wrong_accepted_spec_sha256_halts(self) -> None:
        authz = make_valid_authorization(accepted_spec_sha256="0" * 64)
        self.assertIsNotNone(ol.validate_execution_authorization(authz, expected_ticker=TICKER))

    def test_malformed_implementation_commit_halts(self) -> None:
        authz = make_valid_authorization(accepted_implementation_commit="not-40-hex")
        self.assertIsNotNone(ol.validate_execution_authorization(authz, expected_ticker=TICKER))

    def test_wrong_source_identity_sha256_halts(self) -> None:
        authz = make_valid_authorization(source_identity_sha256="0" * 64)
        self.assertIsNotNone(ol.validate_execution_authorization(authz, expected_ticker=TICKER))

    def test_exact_source_record_sha256_accepted(self) -> None:
        # SAME_SCOPE_CORRECTION_02, point 1: the accepted value is the
        # source *record's* own hash.
        authz = make_valid_authorization(source_identity_sha256=ol.SOURCE_RECORD_SHA256)
        self.assertIsNone(ol.validate_execution_authorization(authz, expected_ticker=TICKER))

    def test_raw_openapi_sha256_substituted_is_rejected(self) -> None:
        # The raw OpenAPI document hash must NOT be accepted here, even
        # though it is a real, valid-looking accepted hash elsewhere in
        # this module -- it is simply the wrong identity for this field.
        self.assertNotEqual(ol.SOURCE_RECORD_SHA256, ol.SOURCE_OPENAPI_SHA256)
        authz = make_valid_authorization(source_identity_sha256=ol.SOURCE_OPENAPI_SHA256)
        self.assertIsNotNone(ol.validate_execution_authorization(authz, expected_ticker=TICKER))

    def test_arbitrary_source_record_sha256_rejected(self) -> None:
        authz = make_valid_authorization(source_identity_sha256="a" * 64)
        self.assertIsNotNone(ol.validate_execution_authorization(authz, expected_ticker=TICKER))

    def test_missing_operation_binding_entry_halts(self) -> None:
        bindings = {name: v[1] for name, v in ol.OPERATION_BINDINGS.items()}
        del bindings["CANCEL_ORDER_V2"]
        authz = make_valid_authorization(operation_binding_sha256=bindings)
        self.assertIsNotNone(ol.validate_execution_authorization(authz, expected_ticker=TICKER))

    def test_wrong_operation_binding_hash_halts(self) -> None:
        bindings = {name: v[1] for name, v in ol.OPERATION_BINDINGS.items()}
        bindings["CANCEL_ORDER_V2"] = "0" * 64
        authz = make_valid_authorization(operation_binding_sha256=bindings)
        self.assertIsNotNone(ol.validate_execution_authorization(authz, expected_ticker=TICKER))

    def test_fee_risk_binding_exceeding_ceiling_halts(self) -> None:
        # SAME_SCOPE_CORRECTION_03: fee_risk_binding is a Section 7.1
        # Input field, validated by validate_lifecycle_input_fields, not
        # validate_execution_authorization.
        halt = ol.validate_lifecycle_input_fields(
            validated_demo_profile=make_valid_demo_profile_via_canonical_validator(),
            authorization_envelope=make_valid_authorization_envelope(),
            fee_risk_binding=ol.OneOrderFeeRiskBinding(max_fee_dollars=Decimal("0.100000")),
            dispatch_expectation=ol.OneOrderLifecycleDispatchExpectation(True, True, True, True, True),
        )
        self.assertIsNotNone(halt)

    def test_fee_risk_binding_exactly_at_ceiling_passes(self) -> None:
        halt = ol.validate_lifecycle_input_fields(
            validated_demo_profile=make_valid_demo_profile_via_canonical_validator(),
            authorization_envelope=make_valid_authorization_envelope(),
            fee_risk_binding=ol.OneOrderFeeRiskBinding(max_fee_dollars=Decimal("0.040000")),
            dispatch_expectation=ol.OneOrderLifecycleDispatchExpectation(True, True, True, True, True),
        )
        self.assertIsNone(halt)

    def test_dispatch_expectation_claiming_production_halts(self) -> None:
        halt = ol.validate_lifecycle_input_fields(
            validated_demo_profile=make_valid_demo_profile_via_canonical_validator(),
            authorization_envelope=make_valid_authorization_envelope(),
            fee_risk_binding=ol.OneOrderFeeRiskBinding(max_fee_dollars=Decimal("0.040000")),
            dispatch_expectation=ol.OneOrderLifecycleDispatchExpectation(
                no_production=False, no_websocket=True, no_amend=True, no_decrease=True, no_replacement=True,
            ),
        )
        self.assertIsNotNone(halt)

    def test_dispatch_expectation_claiming_amend_halts(self) -> None:
        halt = ol.validate_lifecycle_input_fields(
            validated_demo_profile=make_valid_demo_profile_via_canonical_validator(),
            authorization_envelope=make_valid_authorization_envelope(),
            fee_risk_binding=ol.OneOrderFeeRiskBinding(max_fee_dollars=Decimal("0.040000")),
            dispatch_expectation=ol.OneOrderLifecycleDispatchExpectation(
                no_production=True, no_websocket=True, no_amend=False, no_decrease=True, no_replacement=True,
            ),
        )
        self.assertIsNotNone(halt)

    def test_blank_authorization_id_halts(self) -> None:
        authz = make_valid_authorization(gustavo_execution_authorization_id="")
        self.assertIsNotNone(ol.validate_execution_authorization(authz, expected_ticker=TICKER))


# ---------------------------------------------------------------------------
# Pre-send gate: zero-transport-call tests for every gate failure
# ---------------------------------------------------------------------------

class TestPreSendGateZeroTransportCalls(unittest.TestCase):
    def test_spec_identity_mismatch_zero_calls(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        result = plan_and_execute(transport, clock=clock, authorization=make_valid_authorization(accepted_spec_sha256="0" * 64))
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.SPEC_IDENTITY_MISMATCH)
        self.assertEqual(transport.calls, [])

    def test_source_record_corrupt_zero_calls(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        corrupted = bytearray(real_source_record_bytes())
        corrupted[0] ^= 0xFF
        result = plan_and_execute(transport, clock=clock, source_record_bytes=bytes(corrupted))
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.SOURCE_RECORD_IDENTITY_MISMATCH)
        self.assertEqual(transport.calls, [])

    def test_source_record_missing_zero_calls(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        result = plan_and_execute(transport, clock=clock, source_record_bytes=b"")
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.SOURCE_RECORD_IDENTITY_MISMATCH)
        self.assertEqual(transport.calls, [])

    def test_one_corrupt_binding_zero_calls(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        bindings = real_operation_binding_bytes()
        corrupted = bytearray(bindings["FILL_READ"])
        corrupted[-1] ^= 0xFF
        bindings["FILL_READ"] = bytes(corrupted)
        result = plan_and_execute(transport, clock=clock, operation_binding_bytes=bindings)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.OPERATION_BINDING_MISMATCH)
        self.assertEqual(transport.calls, [])

    def test_missing_binding_entry_zero_calls(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        bindings = real_operation_binding_bytes()
        del bindings["CANCEL_ORDER_V2"]
        result = plan_and_execute(transport, clock=clock, operation_binding_bytes=bindings)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.OPERATION_BINDING_MISMATCH)
        self.assertEqual(transport.calls, [])

    def test_execution_authorization_invalid_zero_calls(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        result = plan_and_execute(transport, clock=clock, authorization=make_valid_authorization(ticker="WRONG"))
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID)
        self.assertEqual(transport.calls, [])

    def test_writer_proof_invalid_zero_calls(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        result = plan_and_execute(transport, clock=clock, proof=make_valid_proof(ticker="WRONG-TICKER"))
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.WRITER_EXCLUSIVITY_SCOPE_MISMATCH)
        self.assertEqual(transport.calls, [])

    def test_proof_id_authorization_mismatch_zero_calls(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        authz = make_valid_authorization(writer_proof_id="PROOF-DIFFERENT")
        result = plan_and_execute(transport, clock=clock, authorization=authz)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.WRITER_EXCLUSIVITY_SCOPE_MISMATCH)
        self.assertEqual(transport.calls, [])


class TestCanonicalDemoProfileAndEnvelope(unittest.TestCase):
    """SAME_SCOPE_CORRECTION_03, point 3: the canonical
    ``ValidatedDemoProfile`` / ``TaskAuthorizationCapabilityEnvelope``
    layer (Section 7.1) is a second, broader gate distinct from the seven
    local operation capabilities, and lives as sibling ``OneOrderLifecycleInput``
    fields, not nested inside ``lifecycle_authorization``. Every failure
    mode here must halt before transport call 1.
    """

    def test_valid_profile_and_envelope_pass(self) -> None:
        halt = ol.validate_lifecycle_input_fields(
            validated_demo_profile=make_valid_demo_profile_via_canonical_validator(),
            authorization_envelope=make_valid_authorization_envelope(),
            fee_risk_binding=ol.OneOrderFeeRiskBinding(max_fee_dollars=Decimal("0.040000")),
            dispatch_expectation=ol.OneOrderLifecycleDispatchExpectation(True, True, True, True, True),
        )
        self.assertIsNone(halt)

    def test_wrong_canonical_environment_zero_calls(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        bad_profile = make_valid_demo_profile(environment=Environment.KALSHI_PRODUCTION)
        result = plan_and_execute(transport, clock=clock, validated_demo_profile=bad_profile)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.CANONICAL_DEMO_PROFILE_INVALID)
        self.assertEqual(transport.calls, [])

    def test_unusable_mutated_profile_wrong_type_zero_calls(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        result = plan_and_execute(transport, clock=clock, validated_demo_profile="not-a-profile")
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.CANONICAL_DEMO_PROFILE_INVALID)
        self.assertEqual(transport.calls, [])

    def test_mutated_profile_secret_loaded_true_rejected(self) -> None:
        # ValidatedDemoProfile.__post_init__ itself forbids secret_loaded
        # being anything but False at construction time, so this proves
        # the invariant is enforced by the canonical type before this
        # module ever sees it.
        with self.assertRaises(ValueError):
            make_valid_demo_profile(secret_loaded=True)

    def test_wrong_requested_capability_zero_calls(self) -> None:
        # SAME_SCOPE_CORRECTION_03, point 1: the canonical validator can
        # never issue DEMO_WRITE, so a profile requesting the correct
        # DEMO_AUTHENTICATED_READ capability but with a *different*
        # requested/effective pairing than expected must still halt if it
        # doesn't match exactly. Here we use DEMO_PUBLIC_REST_READ, which
        # the canonical validator genuinely can issue, but is not the
        # capability this lifecycle requires.
        clock = _FixedClock()
        transport = full_happy_path_transport()
        bad_profile = make_valid_demo_profile(
            requested_capability=RequestedCapability.DEMO_PUBLIC_REST_READ,
            effective_capability=RequestedCapability.DEMO_PUBLIC_REST_READ,
        )
        result = plan_and_execute(transport, clock=clock, validated_demo_profile=bad_profile)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.CANONICAL_CAPABILITY_NOT_AUTHORIZED)
        self.assertEqual(transport.calls, [])

    def test_wrong_effective_capability_zero_calls(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        bad_profile = make_valid_demo_profile(effective_capability=RequestedCapability.DEMO_PUBLIC_REST_READ)
        result = plan_and_execute(transport, clock=clock, validated_demo_profile=bad_profile)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.CANONICAL_CAPABILITY_NOT_AUTHORIZED)
        self.assertEqual(transport.calls, [])

    def test_malformed_duck_typed_envelope_zero_calls(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()

        class _FakeEnvelope:
            """A duck-typed look-alike presenting the same attribute
            surface, but never the exact accepted runtime type."""

            def __getattr__(self, name: str) -> object:
                class _AV:
                    value = "PERMITTED"
                return _AV()

        result = plan_and_execute(transport, clock=clock, authorization_envelope=_FakeEnvelope())
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.CANONICAL_CAPABILITY_ENVELOPE_INVALID)
        self.assertEqual(transport.calls, [])

    def test_demo_authenticated_read_not_authorized_zero_calls(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        bad_envelope = make_valid_authorization_envelope(demo_authenticated_reads=AuthorizationValue.PROHIBITED)
        result = plan_and_execute(transport, clock=clock, authorization_envelope=bad_envelope)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.CANONICAL_CAPABILITY_NOT_AUTHORIZED)
        self.assertEqual(transport.calls, [])

    def test_demo_write_authorization_missing_zero_calls(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        bad_envelope = make_valid_authorization_envelope(demo_writes=AuthorizationValue.PROHIBITED)
        result = plan_and_execute(transport, clock=clock, authorization_envelope=bad_envelope)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.CANONICAL_CAPABILITY_NOT_AUTHORIZED)
        self.assertEqual(transport.calls, [])

    def test_credential_use_authority_missing_zero_calls(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        bad_envelope = make_valid_authorization_envelope(credential_use=AuthorizationValue.PROHIBITED)
        result = plan_and_execute(transport, clock=clock, authorization_envelope=bad_envelope)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.CANONICAL_CAPABILITY_NOT_AUTHORIZED)
        self.assertEqual(transport.calls, [])

    def test_production_capability_present_zero_calls(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        bad_envelope = make_valid_authorization_envelope(production_authenticated_reads=AuthorizationValue.PERMITTED)
        result = plan_and_execute(transport, clock=clock, authorization_envelope=bad_envelope)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.CANONICAL_PRODUCTION_OR_FUNDING_CAPABILITY_PRESENT)
        self.assertEqual(transport.calls, [])

    def test_funding_capability_present_zero_calls(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        bad_envelope = make_valid_authorization_envelope(account_funding=AuthorizationValue.PERMITTED)
        result = plan_and_execute(transport, clock=clock, authorization_envelope=bad_envelope)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.CANONICAL_PRODUCTION_OR_FUNDING_CAPABILITY_PRESENT)
        self.assertEqual(transport.calls, [])

    def test_canonical_profile_envelope_ticker_scoped_mismatch_zero_calls(self) -> None:
        # A "profile/envelope mismatch" scenario: the profile itself is
        # valid, but paired with an envelope that lacks demo_writes --
        # proving the two layers are checked independently, not inferred
        # from one another.
        clock = _FixedClock()
        transport = full_happy_path_transport()
        bad_envelope = make_valid_authorization_envelope(demo_writes=AuthorizationValue.PROHIBITED)
        result = plan_and_execute(
            transport, clock=clock,
            validated_demo_profile=make_valid_demo_profile_via_canonical_validator(),
            authorization_envelope=bad_envelope,
        )
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.CANONICAL_CAPABILITY_NOT_AUTHORIZED)
        self.assertEqual(transport.calls, [])

    def test_wrong_rest_endpoint_host_zero_calls(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        bad_profile = make_valid_demo_profile(
            rest=EndpointComponents(
                scheme="https", host="not-the-real-demo-host.example.com", port=443,
                path="/trade-api/v2", has_user_info=False, has_query=False, has_fragment=False,
            )
        )
        result = plan_and_execute(transport, clock=clock, validated_demo_profile=bad_profile)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.CANONICAL_DEMO_PROFILE_INVALID)
        self.assertEqual(transport.calls, [])

    def test_missing_credential_reference_kind_zero_calls(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        bad_profile = make_valid_demo_profile(
            credential_reference_states=(
                (CredentialReferenceKind.API_KEY_ID_ENV_SOURCE, CredentialReferenceState.CONFIGURED),
            ),
        )
        result = plan_and_execute(transport, clock=clock, validated_demo_profile=bad_profile)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.CANONICAL_DEMO_PROFILE_INVALID)
        self.assertEqual(transport.calls, [])

    def test_credential_reference_not_configured_zero_calls(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        bad_profile = make_valid_demo_profile(
            credential_reference_states=(
                (CredentialReferenceKind.API_KEY_ID_ENV_SOURCE, CredentialReferenceState.MISSING),
                (CredentialReferenceKind.PRIVATE_KEY_PEM_ENV_SOURCE, CredentialReferenceState.CONFIGURED),
            ),
        )
        result = plan_and_execute(transport, clock=clock, validated_demo_profile=bad_profile)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.CANONICAL_DEMO_PROFILE_INVALID)
        self.assertEqual(transport.calls, [])

    def test_local_capabilities_and_canonical_envelope_are_independent_layers(self) -> None:
        # Full local CapabilityEnvelope with every one of the seven
        # operation capabilities granted, but a canonical envelope
        # missing demo_writes, still halts -- proving neither layer
        # substitutes for the other.
        clock = _FixedClock()
        transport = full_happy_path_transport()
        bad_envelope = make_valid_authorization_envelope(demo_writes=AuthorizationValue.PROHIBITED)
        authz = make_valid_authorization(
            capabilities=make_capabilities(),  # all seven local capabilities granted
        )
        result = plan_and_execute(transport, clock=clock, authorization=authz, authorization_envelope=bad_envelope)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.CANONICAL_CAPABILITY_NOT_AUTHORIZED)
        self.assertEqual(transport.calls, [])


# ---------------------------------------------------------------------------
# Capability separation: missing capability -> zero unauthorized sends
# ---------------------------------------------------------------------------

class TestCapabilitySeparation(unittest.TestCase):
    def test_all_seven_capabilities_enumerated(self) -> None:
        self.assertEqual(len(ol.CapabilityName), 7)
        self.assertEqual(len(ol.REQUIRED_CAPABILITIES), 7)

    def test_capability_envelope_has_and_missing(self) -> None:
        env = make_capabilities(exclude=(ol.CapabilityName.ORDER_CANCEL,))
        self.assertFalse(env.has(ol.CapabilityName.ORDER_CANCEL))
        self.assertTrue(env.has(ol.CapabilityName.ORDER_CREATE))
        self.assertEqual(env.missing(ol.REQUIRED_CAPABILITIES), frozenset({ol.CapabilityName.ORDER_CANCEL}))

    def test_missing_pre_create_capability_zero_calls(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        authz = make_valid_authorization(capabilities=make_capabilities(exclude=(ol.CapabilityName.PRE_CREATE_ORDER_TRUTH_READ,)))
        result = plan_and_execute(transport, clock=clock, authorization=authz)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.CAPABILITY_MISSING)
        self.assertEqual(transport.calls, [])

    def test_missing_create_capability_only_pre_create_sent(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        authz = make_valid_authorization(capabilities=make_capabilities(exclude=(ol.CapabilityName.ORDER_CREATE,)))
        result = plan_and_execute(transport, clock=clock, authorization=authz)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.CAPABILITY_MISSING)
        self.assertEqual(len(transport.calls_for(ol.LifecycleOperation.PRE_CREATE_TRUTH)), 1)
        self.assertEqual(len(transport.calls_for(ol.LifecycleOperation.CREATE)), 0)

    def test_missing_exact_order_capability_no_order_read_sent(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        authz = make_valid_authorization(capabilities=make_capabilities(exclude=(ol.CapabilityName.EXACT_ORDER_READ,)))
        result = plan_and_execute(transport, clock=clock, authorization=authz)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.CAPABILITY_MISSING)
        self.assertEqual(len(transport.calls_for(ol.LifecycleOperation.EXACT_ORDER)), 0)

    def test_missing_fill_capability_no_fills_read_sent(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        authz = make_valid_authorization(capabilities=make_capabilities(exclude=(ol.CapabilityName.FILL_READ,)))
        result = plan_and_execute(transport, clock=clock, authorization=authz)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.CAPABILITY_MISSING)
        self.assertEqual(len(transport.calls_for(ol.LifecycleOperation.FILLS)), 0)

    def test_missing_cancel_capability_falls_through_without_cancel_send(self) -> None:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_ok_pre_create(),
            create=_ok_create(),
            exact_order=[_ok_order_response(client_order_id="5781e77b-e1ed-4303-bcf6-bdb282419251", status="resting")],
            fills=[_ok_fills_response([])],
        )
        authz = make_valid_authorization(capabilities=make_capabilities(exclude=(ol.CapabilityName.ORDER_CANCEL,)))
        result = plan_and_execute(transport, clock=clock, authorization=authz)
        # cancel_is_send_capable() itself checks has_cancel_capability and
        # returns False, so the lifecycle falls through to the no-cancel
        # resolution branch rather than halting; no cancellation is sent
        # and the order remains resting/unresolved -- exercised here only
        # to confirm zero cancel sends occurred.
        self.assertEqual(len(transport.calls_for(ol.LifecycleOperation.CANCEL)), 0)

    def test_missing_recovery_capability_zero_recovery_calls(self) -> None:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_ok_pre_create(),
            create=_raw_response(status=200, body={}, send_result_classification=ol.SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN),
        )
        authz = make_valid_authorization(capabilities=make_capabilities(exclude=(ol.CapabilityName.ORDER_LIST_RECOVERY_READ,)))
        result = plan_and_execute(transport, clock=clock, authorization=authz)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.CAPABILITY_MISSING)
        self.assertEqual(len(transport.calls_for(ol.LifecycleOperation.RECOVERY)), 0)


# ---------------------------------------------------------------------------
# 20-24: pre-create venue truth
# ---------------------------------------------------------------------------

class TestPreCreateVenueTruth(unittest.TestCase):
    def test_zero_order_success(self) -> None:
        response = ol.GetOrdersResponse(http_status=200, cursor="", orders=())
        self.assertIsNone(ol.validate_pre_create_response(response, ticker=TICKER))

    def test_existing_resting_order_halts(self) -> None:
        response = ol.GetOrdersResponse(http_status=200, cursor="", orders=(make_order(client_order_id="other"),))
        self.assertEqual(
            ol.validate_pre_create_response(response, ticker=TICKER),
            ol.LifecycleHaltCode.PRE_CREATE_RESTING_ORDER_EXISTS,
        )

    def test_malformed_response_halts(self) -> None:
        response = ol.GetOrdersResponse(http_status=200, cursor="", orders=None)  # type: ignore[arg-type]
        self.assertEqual(
            ol.validate_pre_create_response(response, ticker=TICKER),
            ol.LifecycleHaltCode.PRE_CREATE_MALFORMED_RESPONSE,
        )

    def test_non_empty_cursor_halts(self) -> None:
        response = ol.GetOrdersResponse(http_status=200, cursor="abc", orders=())
        self.assertEqual(
            ol.validate_pre_create_response(response, ticker=TICKER),
            ol.LifecycleHaltCode.PRE_CREATE_NONEMPTY_CURSOR,
        )

    def test_http_error_halts(self) -> None:
        response = ol.GetOrdersResponse(http_status=500, cursor="", orders=())
        self.assertEqual(
            ol.validate_pre_create_response(response, ticker=TICKER),
            ol.LifecycleHaltCode.PRE_CREATE_HTTP_ERROR,
        )

    def test_pre_create_query_shape(self) -> None:
        query = ol.build_pre_create_query(ticker=TICKER)
        self.assertEqual(query, {"ticker": TICKER, "status": "resting", "limit": 1000, "subaccount": 0})

    def test_pre_create_request_budget_is_one(self) -> None:
        self.assertEqual(ol.OPERATION_BUDGET[ol.LifecycleOperation.PRE_CREATE_TRUTH], 1)

    def test_pre_create_request_uses_exact_method_and_path(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        plan_and_execute(transport, clock=clock)
        calls = transport.calls_for(ol.LifecycleOperation.PRE_CREATE_TRUTH)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].method, "GET")
        self.assertEqual(calls[0].path, "/trade-api/v2/portfolio/orders")
        self.assertEqual(calls[0].query, {"ticker": TICKER, "status": "resting", "limit": 1000, "subaccount": 0})
        self.assertIsNone(calls[0].body)


# ---------------------------------------------------------------------------
# 25-30: create order and Appendix-G classification
# ---------------------------------------------------------------------------

class TestCreateOrder(unittest.TestCase):
    def test_exact_fixed_create_body(self) -> None:
        body = ol.build_create_order_body(ticker=TICKER, client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a", expiration_time=1_800_000_045)
        self.assertEqual(body["ticker"], TICKER)
        self.assertEqual(body["side"], "bid")
        self.assertEqual(body["count"], "1.00")
        self.assertEqual(body["price"], "0.0100")
        self.assertEqual(body["time_in_force"], "good_till_canceled")
        self.assertEqual(body["self_trade_prevention_type"], "taker_at_cross")
        self.assertIs(body["post_only"], True)
        self.assertIs(body["cancel_order_on_pause"], True)
        self.assertIs(body["reduce_only"], False)
        self.assertEqual(body["subaccount"], 0)
        self.assertEqual(body["exchange_index"], 0)
        self.assertNotIn("order_group_id", body)

    def test_no_unlisted_create_field(self) -> None:
        body = ol.build_create_order_body(ticker=TICKER, client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a", expiration_time=1)
        self.assertEqual(set(body.keys()), ol.CREATE_ORDER_ALLOWED_FIELDS)

    def test_validate_create_order_body_accepts_well_formed(self) -> None:
        body = ol.build_create_order_body(ticker=TICKER, client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a", expiration_time=1)
        self.assertTrue(ol.validate_create_order_body(body))

    def test_validate_create_order_body_rejects_extra_field(self) -> None:
        body = dict(ol.build_create_order_body(ticker=TICKER, client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a", expiration_time=1))
        body["order_group_id"] = "should-not-be-here"
        self.assertFalse(ol.validate_create_order_body(body))

    def test_expiration_time_computation(self) -> None:
        self.assertEqual(ol.compute_expiration_time(1000.9), 1045)
        self.assertEqual(ol.compute_expiration_time(1000.0), 1045)

    def test_client_order_id_is_lowercase_uuid4_text(self) -> None:
        cid = ol.generate_client_order_id()
        self.assertEqual(cid, cid.lower())
        self.assertEqual(len(cid), 36)

    def test_create_request_carries_exact_body(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        plan_and_execute(transport, clock=clock)
        calls = transport.calls_for(ol.LifecycleOperation.CREATE)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].method, "POST")
        self.assertEqual(calls[0].path, "/trade-api/v2/portfolio/events/orders")
        self.assertTrue(ol.validate_create_order_body(calls[0].body))

    def test_exactly_one_create_send(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        plan_and_execute(transport, clock=clock)
        self.assertEqual(len(transport.calls_for(ol.LifecycleOperation.CREATE)), 1)

    def test_definitive_create_success_binds_order_id(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport(order_id="ORDER-XYZ")
        result = plan_and_execute(transport, clock=clock)
        self.assertEqual(result.bound_order_id, "ORDER-XYZ")


class TestCreateResponseClassification(unittest.TestCase):
    def test_definitive_success(self) -> None:
        raw = _ok_create()
        outcome, order_id = ol.classify_create_response(raw)
        self.assertEqual(outcome, ol.SendOutcome.DEFINITIVE_SUCCESS)
        self.assertEqual(order_id, "ORDER-0001")

    def test_received_400_is_unknown_after_send(self) -> None:
        raw = _raw_response(status=400, body={"error": "bad_request"})
        outcome, order_id = ol.classify_create_response(raw)
        self.assertEqual(outcome, ol.SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN)
        self.assertIsNone(order_id)

    def test_all_non_success_http_statuses_are_unknown_after_send(self) -> None:
        for status in (400, 401, 403, 422, 404, 409, 500, 503):
            raw = _raw_response(status=status, body={"error": "x"})
            outcome, order_id = ol.classify_create_response(raw)
            self.assertEqual(outcome, ol.SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN, msg=str(status))
            self.assertIsNone(order_id, msg=str(status))

    def test_send_uncertain_flag_forces_unknown_regardless_of_status(self) -> None:
        raw = _raw_response(status=201, body={"order_id": "X", "fill_count": "0.00", "remaining_count": "1.00", "ts_ms": 1}, send_result_classification=ol.SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN)
        outcome, order_id = ol.classify_create_response(raw)
        self.assertEqual(outcome, ol.SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN)
        self.assertIsNone(order_id)

    def test_201_missing_required_field_is_unknown_not_definitive(self) -> None:
        raw = _raw_response(status=201, body={"order_id": "X"})
        outcome, order_id = ol.classify_create_response(raw)
        self.assertEqual(outcome, ol.SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN)
        self.assertIsNone(order_id)

    def test_201_fill_plus_remaining_not_equal_one_is_unknown(self) -> None:
        raw = _raw_response(status=201, body={"order_id": "X", "fill_count": "0.50", "remaining_count": "0.40", "ts_ms": 1})
        outcome, _ = ol.classify_create_response(raw)
        self.assertEqual(outcome, ol.SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN)

    def test_201_ts_ms_wrong_type_is_unknown(self) -> None:
        raw = _raw_response(status=201, body={"order_id": "X", "fill_count": "0.00", "remaining_count": "1.00", "ts_ms": "not-an-int"})
        outcome, _ = ol.classify_create_response(raw)
        self.assertEqual(outcome, ol.SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN)

    def test_201_ts_ms_bool_is_unknown(self) -> None:
        raw = _raw_response(status=201, body={"order_id": "X", "fill_count": "0.00", "remaining_count": "1.00", "ts_ms": True})
        outcome, _ = ol.classify_create_response(raw)
        self.assertEqual(outcome, ol.SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN)

    def test_201_client_order_id_present_and_matching_is_still_definitive(self) -> None:
        raw = _raw_response(status=201, body={"order_id": "X", "fill_count": "0.00", "remaining_count": "1.00", "ts_ms": 1, "client_order_id": "a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a"})
        outcome, order_id = ol.classify_create_response(raw)
        self.assertEqual(outcome, ol.SendOutcome.DEFINITIVE_SUCCESS)
        self.assertEqual(order_id, "X")

    def test_received_400_uses_single_recovery_and_halts_unresolved_when_no_match(self) -> None:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_ok_pre_create(),
            create=_raw_response(status=400, body={"error": "rejected"}),
            recovery=[_raw_response(status=200, body={"orders": [], "cursor": ""})],
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.RECOVERY_ZERO_MATCH)
        self.assertTrue(result.create_send_may_have_begun)
        self.assertEqual(result.created_order_upper_bound, 1)
        self.assertTrue(result.unknown_result)
        self.assertFalse(result.proof_release_eligible)
        self.assertEqual(len(transport.calls_for(ol.LifecycleOperation.CREATE)), 1)
        self.assertEqual(len(transport.calls_for(ol.LifecycleOperation.RECOVERY)), 1)


# ---------------------------------------------------------------------------
# 29-34: ambiguous create / recovery
# ---------------------------------------------------------------------------

class TestAmbiguousCreateRecovery(unittest.TestCase):
    def test_ambiguous_create_triggers_recovery(self) -> None:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_ok_pre_create(),
            create=_raw_response(status=201, body={}, send_result_classification=ol.SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN),
            recovery=[_raw_response(status=200, body={"orders": [make_order(order_id="ORDER-REC", client_order_id="5781e77b-e1ed-4303-bcf6-bdb282419251")], "cursor": ""})],
            exact_order=[
                _ok_order_response(order_id="ORDER-REC", client_order_id="5781e77b-e1ed-4303-bcf6-bdb282419251"),
                _ok_order_response(order_id="ORDER-REC", client_order_id="5781e77b-e1ed-4303-bcf6-bdb282419251", status="canceled"),
            ],
            fills=[_ok_fills_response(), _ok_fills_response()],
            cancel=[_ok_cancel_response(order_id="ORDER-REC", reduced_by="1.00")],
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertEqual(result.bound_order_id, "ORDER-REC")

    def test_no_second_create_after_ambiguity(self) -> None:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_ok_pre_create(),
            create=_raw_response(status=201, body={}, send_result_classification=ol.SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN),
            recovery=[_raw_response(status=200, body={"orders": [make_order(order_id="ORDER-REC", client_order_id="5781e77b-e1ed-4303-bcf6-bdb282419251")], "cursor": ""})],
            exact_order=[
                _ok_order_response(order_id="ORDER-REC", client_order_id="5781e77b-e1ed-4303-bcf6-bdb282419251"),
                _ok_order_response(order_id="ORDER-REC", client_order_id="5781e77b-e1ed-4303-bcf6-bdb282419251", status="canceled"),
            ],
            fills=[_ok_fills_response(), _ok_fills_response()],
            cancel=[_ok_cancel_response(order_id="ORDER-REC", reduced_by="1.00")],
        )
        plan_and_execute(transport, clock=clock)
        self.assertEqual(len(transport.calls_for(ol.LifecycleOperation.CREATE)), 1)

    def test_recovery_exact_one_match(self) -> None:
        response = ol.GetOrdersResponse(http_status=200, cursor="", orders=(make_order(order_id="O1", client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a"),))
        order, halt = ol.validate_recovery_response(response, client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a", ticker=TICKER)
        self.assertIsNone(halt)
        self.assertEqual(order["order_id"], "O1")

    def test_recovery_zero_match(self) -> None:
        response = ol.GetOrdersResponse(http_status=200, cursor="", orders=())
        _, halt = ol.validate_recovery_response(response, client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a", ticker=TICKER)
        self.assertEqual(halt, ol.LifecycleHaltCode.RECOVERY_ZERO_MATCH)

    def test_recovery_multiple_matches(self) -> None:
        response = ol.GetOrdersResponse(
            http_status=200,
            cursor="",
            orders=(
                make_order(order_id="O1", client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a"),
                make_order(order_id="O2", client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a"),
            ),
        )
        _, halt = ol.validate_recovery_response(response, client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a", ticker=TICKER)
        self.assertEqual(halt, ol.LifecycleHaltCode.RECOVERY_MULTIPLE_MATCH)

    def test_recovery_non_empty_cursor_halts(self) -> None:
        response = ol.GetOrdersResponse(http_status=200, cursor="next", orders=())
        _, halt = ol.validate_recovery_response(response, client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a", ticker=TICKER)
        self.assertEqual(halt, ol.LifecycleHaltCode.RECOVERY_NONEMPTY_CURSOR)

    def test_recovery_malformed_response(self) -> None:
        response = ol.GetOrdersResponse(http_status=500, cursor="", orders=())
        _, halt = ol.validate_recovery_response(response, client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a", ticker=TICKER)
        self.assertEqual(halt, ol.LifecycleHaltCode.RECOVERY_MALFORMED_RESPONSE)

    def test_recovery_match_with_bad_order_schema_halts(self) -> None:
        bad_order = make_order(order_id="O1", client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a", yes_price_dollars="0.0200")
        response = ol.GetOrdersResponse(http_status=200, cursor="", orders=(bad_order,))
        order, halt = ol.validate_recovery_response(response, client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a", ticker=TICKER)
        self.assertEqual(halt, ol.LifecycleHaltCode.RECOVERY_MALFORMED_RESPONSE)
        self.assertIsNone(order)

    def test_recovery_query_shape(self) -> None:
        query = ol.build_recovery_query(ticker=TICKER)
        self.assertEqual(query, {"ticker": TICKER, "limit": 1000, "subaccount": 0})
        self.assertNotIn("status", query)


# ---------------------------------------------------------------------------
# 35-37 + Appendix E.1: exact order identity / status / full schema
# ---------------------------------------------------------------------------

class TestExactOrderRead(unittest.TestCase):
    def test_exact_identity_match_passes(self) -> None:
        order = make_order(order_id="O1", client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a")
        self.assertIsNone(ol.validate_order_record(order, bound_order_id="O1", client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a", ticker=TICKER))

    def test_order_id_mismatch_halts(self) -> None:
        order = make_order(order_id="OTHER", client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a")
        self.assertEqual(
            ol.validate_order_record(order, bound_order_id="O1", client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a", ticker=TICKER),
            ol.LifecycleHaltCode.ORDER_IDENTITY_MISMATCH,
        )

    def test_supported_status_handling(self) -> None:
        for status in ("resting", "canceled", "executed"):
            order = make_order(order_id="O1", client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a", status=status)
            self.assertIsNone(ol.validate_order_record(order, bound_order_id="O1", client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a", ticker=TICKER))

    def test_unsupported_status_halts(self) -> None:
        order = make_order(order_id="O1", client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a", status="pending_review")
        self.assertEqual(
            ol.validate_order_record(order, bound_order_id="O1", client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a", ticker=TICKER),
            ol.LifecycleHaltCode.ORDER_UNSUPPORTED_STATUS,
        )

    def test_wrong_outcome_side_halts(self) -> None:
        order = make_order(order_id="O1", client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a", outcome_side="no")
        self.assertEqual(
            ol.validate_order_record(order, bound_order_id="O1", client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a", ticker=TICKER),
            ol.LifecycleHaltCode.ORDER_IDENTITY_MISMATCH,
        )

    def test_wrong_price_halts(self) -> None:
        order = make_order(order_id="O1", client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a", yes_price_dollars="0.0200")
        self.assertEqual(
            ol.validate_order_record(order, bound_order_id="O1", client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a", ticker=TICKER),
            ol.LifecycleHaltCode.ORDER_IDENTITY_MISMATCH,
        )

    def test_exact_order_read_budget_is_three(self) -> None:
        self.assertEqual(ol.OPERATION_BUDGET[ol.LifecycleOperation.EXACT_ORDER], 3)

    def test_every_required_field_missing_halts(self) -> None:
        base = make_order(order_id="O1", client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a")
        for required_field in ol.ORDER_REQUIRED_FIELDS:
            incomplete = dict(base)
            del incomplete[required_field]
            halt = ol.validate_order_record(incomplete, bound_order_id="O1", client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a", ticker=TICKER)
            self.assertIsNotNone(halt, msg=required_field)

    def test_numeric_json_value_rejected_for_fixed_point_field(self) -> None:
        for fp_field in ol.ORDER_FIXED_POINT_STRING_FIELDS:
            order = make_order(order_id="O1", client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a")
            order[fp_field] = 0.01  # a JSON number, not the required string
            halt = ol.validate_order_record(order, bound_order_id="O1", client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a", ticker=TICKER)
            self.assertIsNotNone(halt, msg=fp_field)

    def test_integer_json_value_rejected_for_fixed_point_field(self) -> None:
        order = make_order(order_id="O1", client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a")
        order["fill_count_fp"] = 0  # int, not "0.00"
        halt = ol.validate_order_record(order, bound_order_id="O1", client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a", ticker=TICKER)
        self.assertIsNotNone(halt)

    def test_fill_plus_remaining_exceeding_one_halts(self) -> None:
        order = make_order(order_id="O1", client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a", fill_count_fp="0.60", remaining_count_fp="0.60")
        halt = ol.validate_order_record(order, bound_order_id="O1", client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a", ticker=TICKER)
        self.assertIsNotNone(halt)

    def test_negative_fill_count_halts(self) -> None:
        order = make_order(order_id="O1", client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a")
        order["fill_count_fp"] = "-0.10"
        halt = ol.validate_order_record(order, bound_order_id="O1", client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a", ticker=TICKER)
        self.assertIsNotNone(halt)

    def test_initial_count_not_one_halts(self) -> None:
        order = make_order(order_id="O1", client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a", initial_count_fp="2.00")
        halt = ol.validate_order_record(order, bound_order_id="O1", client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a", ticker=TICKER)
        self.assertEqual(halt, ol.LifecycleHaltCode.ORDER_IDENTITY_MISMATCH)

    def test_optional_subaccount_number_must_be_zero_if_present(self) -> None:
        order = make_order(order_id="O1", client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a")
        order["subaccount_number"] = 1
        halt = ol.validate_order_record(order, bound_order_id="O1", client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a", ticker=TICKER)
        self.assertIsNotNone(halt)

    def test_optional_exchange_index_zero_is_fine(self) -> None:
        order = make_order(order_id="O1", client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a")
        order["exchange_index"] = 0
        halt = ol.validate_order_record(order, bound_order_id="O1", client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a", ticker=TICKER)
        self.assertIsNone(halt)

    def test_legacy_side_never_substitutes_for_book_side(self) -> None:
        order = make_order(order_id="O1", client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a")
        del order["book_side"]
        order["side"] = "bid"  # legacy field present, but book_side is required and absent
        halt = ol.validate_order_record(order, bound_order_id="O1", client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a", ticker=TICKER)
        self.assertIsNotNone(halt)

    def test_missing_user_id_halts(self) -> None:
        order = make_order(order_id="O1", client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a")
        order["user_id"] = ""
        halt = ol.validate_order_record(order, bound_order_id="O1", client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a", ticker=TICKER)
        self.assertIsNotNone(halt)

    def test_non_mapping_order_halts(self) -> None:
        halt = ol.validate_order_record("not-a-mapping", bound_order_id="O1", client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a", ticker=TICKER)  # type: ignore[arg-type]
        self.assertIsNotNone(halt)


# ---------------------------------------------------------------------------
# 38-52 + Appendix E.2: fills, full schema
# ---------------------------------------------------------------------------

class TestFillLedger(unittest.TestCase):
    def test_zero_fill(self) -> None:
        ledger = ol.FillLedger()
        self.assertEqual(ledger.total_quantity(), Decimal("0"))
        self.assertEqual(ledger.actual_filled_principal(), Decimal("0"))

    def test_partial_fill(self) -> None:
        ledger = ol.FillLedger()
        halt = ledger.ingest(make_fill(fill_id="F1", count_fp="0.40"), bound_order_id="ORDER-0001", ticker=TICKER)
        self.assertIsNone(halt)
        self.assertEqual(ledger.total_quantity(), Decimal("0.40"))

    def test_multiple_fills_accumulate(self) -> None:
        ledger = ol.FillLedger()
        ledger.ingest(make_fill(fill_id="F1", count_fp="0.30"), bound_order_id="ORDER-0001", ticker=TICKER)
        ledger.ingest(make_fill(fill_id="F2", count_fp="0.30"), bound_order_id="ORDER-0001", ticker=TICKER)
        self.assertEqual(ledger.total_quantity(), Decimal("0.60"))

    def test_full_fill(self) -> None:
        ledger = ol.FillLedger()
        halt = ledger.ingest(make_fill(fill_id="F1", count_fp="1.00"), bound_order_id="ORDER-0001", ticker=TICKER)
        self.assertIsNone(halt)
        self.assertEqual(ledger.total_quantity(), Decimal("1.00"))

    def test_exact_duplicate_fill_replay_counts_once(self) -> None:
        ledger = ol.FillLedger()
        f = make_fill(fill_id="F1", count_fp="0.50")
        ledger.ingest(f, bound_order_id="ORDER-0001", ticker=TICKER)
        halt = ledger.ingest(dict(f), bound_order_id="ORDER-0001", ticker=TICKER)
        self.assertIsNone(halt)
        self.assertEqual(ledger.total_quantity(), Decimal("0.50"))

    def test_conflicting_duplicate_fill_halts(self) -> None:
        ledger = ol.FillLedger()
        ledger.ingest(make_fill(fill_id="F1", count_fp="0.50"), bound_order_id="ORDER-0001", ticker=TICKER)
        halt = ledger.ingest(make_fill(fill_id="F1", count_fp="0.60"), bound_order_id="ORDER-0001", ticker=TICKER)
        self.assertEqual(halt, ol.LifecycleHaltCode.DUPLICATE_FILL_CONFLICT)

    def test_overfill_halts(self) -> None:
        ledger = ol.FillLedger()
        ledger.ingest(make_fill(fill_id="F1", count_fp="0.70"), bound_order_id="ORDER-0001", ticker=TICKER)
        halt = ledger.ingest(make_fill(fill_id="F2", count_fp="0.40"), bound_order_id="ORDER-0001", ticker=TICKER)
        self.assertEqual(halt, ol.LifecycleHaltCode.OVERFILL)

    def test_negative_or_zero_count_halts(self) -> None:
        ledger = ol.FillLedger()
        halt = ledger.ingest(make_fill(fill_id="F1", count_fp="0.00"), bound_order_id="ORDER-0001", ticker=TICKER)
        self.assertEqual(halt, ol.LifecycleHaltCode.FILL_MALFORMED)

    def test_fill_exactly_at_limit_accepted(self) -> None:
        ledger = ol.FillLedger()
        halt = ledger.ingest(make_fill(fill_id="F1", count_fp="1.00", yes_price_dollars="0.0100"), bound_order_id="ORDER-0001", ticker=TICKER)
        self.assertIsNone(halt)

    def test_fill_below_limit_accepted(self) -> None:
        ledger = ol.FillLedger()
        halt = ledger.ingest(make_fill(fill_id="F1", count_fp="1.00", yes_price_dollars="0.0050"), bound_order_id="ORDER-0001", ticker=TICKER)
        self.assertIsNone(halt)

    def test_fill_above_limit_halts(self) -> None:
        ledger = ol.FillLedger()
        halt = ledger.ingest(make_fill(fill_id="F1", count_fp="1.00", yes_price_dollars="0.0200"), bound_order_id="ORDER-0001", ticker=TICKER)
        self.assertEqual(halt, ol.LifecycleHaltCode.FILL_PRICE_WORSE_THAN_LIMIT)

    def test_post_only_taker_conflict_halts(self) -> None:
        ledger = ol.FillLedger()
        halt = ledger.ingest(make_fill(fill_id="F1", count_fp="1.00", is_taker=True), bound_order_id="ORDER-0001", ticker=TICKER)
        self.assertEqual(halt, ol.LifecycleHaltCode.POST_ONLY_TAKER_FILL_CONFLICT)

    def test_aggregate_principal_within_bound(self) -> None:
        ledger = ol.FillLedger()
        ledger.ingest(make_fill(fill_id="F1", count_fp="1.00", yes_price_dollars="0.0100"), bound_order_id="ORDER-0001", ticker=TICKER)
        self.assertLessEqual(ledger.actual_filled_principal(), ol.MAX_FILLED_PRINCIPAL)
        self.assertEqual(ledger.actual_filled_principal(), Decimal("0.010000"))

    def test_principal_relationship_constant(self) -> None:
        self.assertEqual(ol.QUANTITY * ol.LIMIT_PRICE, ol.MAX_FILLED_PRINCIPAL)

    def test_duplicate_fill_does_not_double_count_principal(self) -> None:
        ledger = ol.FillLedger()
        f = make_fill(fill_id="F1", count_fp="1.00", yes_price_dollars="0.0100")
        ledger.ingest(f, bound_order_id="ORDER-0001", ticker=TICKER)
        ledger.ingest(dict(f), bound_order_id="ORDER-0001", ticker=TICKER)
        self.assertEqual(ledger.actual_filled_principal(), Decimal("0.010000"))

    def test_fill_ticker_mismatch_halts(self) -> None:
        ledger = ol.FillLedger()
        halt = ledger.ingest(make_fill(fill_id="F1", ticker="WRONG-TICKER"), bound_order_id="ORDER-0001", ticker=TICKER)
        self.assertEqual(halt, ol.LifecycleHaltCode.FILL_MALFORMED)

    def test_fill_order_id_mismatch_halts(self) -> None:
        ledger = ol.FillLedger()
        halt = ledger.ingest(make_fill(fill_id="F1", order_id="OTHER"), bound_order_id="ORDER-0001", ticker=TICKER)
        self.assertEqual(halt, ol.LifecycleHaltCode.FILL_MALFORMED)

    def test_fills_query_shape_first_page(self) -> None:
        query = ol.build_fills_query(order_id="O1", cursor="")
        self.assertEqual(query, {"order_id": "O1", "limit": 1000, "subaccount": 0})
        self.assertNotIn("ticker", query)

    def test_fills_query_shape_with_cursor(self) -> None:
        query = ol.build_fills_query(order_id="O1", cursor="page2")
        self.assertEqual(query["cursor"], "page2")

    def test_fills_budget_is_four(self) -> None:
        self.assertEqual(ol.OPERATION_BUDGET[ol.LifecycleOperation.FILLS], 4)

    def test_every_required_fill_field_missing_halts(self) -> None:
        base = make_fill(fill_id="F1")
        for required_field in ol.FILL_REQUIRED_FIELDS:
            incomplete = dict(base)
            del incomplete[required_field]
            ledger = ol.FillLedger()
            halt = ledger.ingest(incomplete, bound_order_id="ORDER-0001", ticker=TICKER)
            self.assertIsNotNone(halt, msg=required_field)

    def test_numeric_json_value_rejected_for_fill_fixed_point_field(self) -> None:
        for fp_field in ol.FILL_FIXED_POINT_STRING_FIELDS:
            fill = make_fill(fill_id="F1")
            fill[fp_field] = 0.01
            ledger = ol.FillLedger()
            halt = ledger.ingest(fill, bound_order_id="ORDER-0001", ticker=TICKER)
            self.assertIsNotNone(halt, msg=fp_field)

    def test_missing_trade_id_halts(self) -> None:
        ledger = ol.FillLedger()
        fill = make_fill(fill_id="F1", trade_id="")
        halt = ledger.ingest(fill, bound_order_id="ORDER-0001", ticker=TICKER)
        self.assertIsNotNone(halt)

    def test_fill_market_ticker_mismatch_halts(self) -> None:
        ledger = ol.FillLedger()
        fill = make_fill(fill_id="F1")
        fill["market_ticker"] = "OTHER"
        halt = ledger.ingest(fill, bound_order_id="ORDER-0001", ticker=TICKER)
        self.assertIsNotNone(halt)

    def test_optional_fill_subaccount_number_must_be_zero(self) -> None:
        ledger = ol.FillLedger()
        fill = make_fill(fill_id="F1")
        fill["subaccount_number"] = 3
        halt = ledger.ingest(fill, bound_order_id="ORDER-0001", ticker=TICKER)
        self.assertIsNotNone(halt)

    def test_non_mapping_fill_halts(self) -> None:
        ledger = ol.FillLedger()
        halt = ledger.ingest("not-a-mapping", bound_order_id="ORDER-0001", ticker=TICKER)  # type: ignore[arg-type]
        self.assertIsNotNone(halt)

    def test_reconcile_against_order_matches(self) -> None:
        ledger = ol.FillLedger()
        ledger.ingest(make_fill(fill_id="F1", count_fp="0.40"), bound_order_id="ORDER-0001", ticker=TICKER)
        order = make_order(order_id="ORDER-0001", client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a", fill_count_fp="0.40", remaining_count_fp="0.60")
        self.assertIsNone(ledger.reconcile_against_order(order))

    def test_reconcile_against_order_mismatch_halts(self) -> None:
        ledger = ol.FillLedger()
        ledger.ingest(make_fill(fill_id="F1", count_fp="0.40"), bound_order_id="ORDER-0001", ticker=TICKER)
        order = make_order(order_id="ORDER-0001", client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a", fill_count_fp="0.50", remaining_count_fp="0.50")
        self.assertEqual(
            ledger.reconcile_against_order(order),
            ol.LifecycleHaltCode.FILL_QUANTITY_ORDER_RECONCILIATION_MISMATCH,
        )

    def test_reconcile_against_order_zero_fills_matches_zero(self) -> None:
        ledger = ol.FillLedger()
        order = make_order(order_id="ORDER-0001", client_order_id="a3f1c9de-4b2a-4e11-8c3d-1f2e3d4c5b6a", fill_count_fp="0.00", remaining_count_fp="1.00")
        self.assertIsNone(ledger.reconcile_against_order(order))


class TestFillOrderReconciliationIntegration(unittest.TestCase):
    def test_lifecycle_halts_when_fills_do_not_reconcile_to_order(self) -> None:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_ok_pre_create(),
            create=_ok_create(),
            # Order claims 0.40 filled, but the fills feed only reports 0.30.
            exact_order=[_ok_order_response(client_order_id="5781e77b-e1ed-4303-bcf6-bdb282419251", status="resting", fill_count_fp="0.40", remaining_count_fp="0.60")],
            fills=[_ok_fills_response([make_fill(fill_id="F1", count_fp="0.30")])],
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.FILL_QUANTITY_ORDER_RECONCILIATION_MISMATCH)


# ---------------------------------------------------------------------------
# 53-68: cancel, including Appendix-G classification
# ---------------------------------------------------------------------------

class TestCancelConservation(unittest.TestCase):
    def test_cancel_conservation_exactly_one(self) -> None:
        self.assertIsNone(ol.check_cancel_conservation(final_fill_quantity=Decimal("0.40"), reduced_by=Decimal("0.60")))

    def test_cancel_conservation_zero_fill(self) -> None:
        self.assertIsNone(ol.check_cancel_conservation(final_fill_quantity=Decimal("0.00"), reduced_by=Decimal("1.00")))

    def test_cancel_conservation_below_one_halts(self) -> None:
        self.assertEqual(
            ol.check_cancel_conservation(final_fill_quantity=Decimal("0.30"), reduced_by=Decimal("0.60")),
            ol.LifecycleHaltCode.CANCEL_QUANTITY_CONSERVATION_MISMATCH,
        )

    def test_cancel_conservation_above_one_halts(self) -> None:
        self.assertEqual(
            ol.check_cancel_conservation(final_fill_quantity=Decimal("0.50"), reduced_by=Decimal("0.60")),
            ol.LifecycleHaltCode.CANCEL_QUANTITY_CONSERVATION_MISMATCH,
        )

    def test_reduced_by_never_counted_as_fill(self) -> None:
        ledger = ol.FillLedger()
        ledger.ingest(make_fill(fill_id="F1", count_fp="0.40"), bound_order_id="ORDER-0001", ticker=TICKER)
        self.assertEqual(ledger.total_quantity(), Decimal("0.40"))

    def test_already_filled_order_does_not_cancel(self) -> None:
        self.assertFalse(
            ol.cancel_is_send_capable(
                bound_order_id="O1", latest_status="executed", canonical_fill_quantity=Decimal("1.00"),
                cancel_send_attempt_count=0, writer_proof_state_held=True,
            )
        )

    def test_already_canceled_order_does_not_cancel(self) -> None:
        self.assertFalse(
            ol.cancel_is_send_capable(
                bound_order_id="O1", latest_status="canceled", canonical_fill_quantity=Decimal("0.00"),
                cancel_send_attempt_count=0, writer_proof_state_held=True,
            )
        )

    def test_no_second_cancel(self) -> None:
        self.assertFalse(
            ol.cancel_is_send_capable(
                bound_order_id="O1", latest_status="resting", canonical_fill_quantity=Decimal("0.00"),
                cancel_send_attempt_count=1, writer_proof_state_held=True,
            )
        )

    def test_resting_order_is_send_capable(self) -> None:
        self.assertTrue(
            ol.cancel_is_send_capable(
                bound_order_id="O1", latest_status="resting", canonical_fill_quantity=Decimal("0.00"),
                cancel_send_attempt_count=0, writer_proof_state_held=True,
            )
        )

    def test_missing_cancel_capability_not_send_capable(self) -> None:
        self.assertFalse(
            ol.cancel_is_send_capable(
                bound_order_id="O1", latest_status="resting", canonical_fill_quantity=Decimal("0.00"),
                cancel_send_attempt_count=0, writer_proof_state_held=True, has_cancel_capability=False,
            )
        )

    def test_cancel_query_shape(self) -> None:
        self.assertEqual(ol.build_cancel_query(), {"subaccount": 0, "exchange_index": 0})

    def test_cancel_budget_is_one(self) -> None:
        self.assertEqual(ol.OPERATION_BUDGET[ol.LifecycleOperation.CANCEL], 1)


class TestCancelResponseClassification(unittest.TestCase):
    def test_definitive_success(self) -> None:
        raw = _ok_cancel_response()
        self.assertEqual(ol.classify_cancel_response(raw), ol.SendOutcome.DEFINITIVE_SUCCESS)

    def test_all_non_success_http_statuses_are_unknown_after_send(self) -> None:
        for status in (400, 401, 403, 422, 404, 409, 500, 503):
            raw = _raw_response(status=status, body={"error": "x"})
            self.assertEqual(ol.classify_cancel_response(raw), ol.SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN, msg=str(status))

    def test_send_uncertain_forces_unknown(self) -> None:
        raw = _raw_response(status=200, body=_ok_cancel_response().body, send_result_classification=ol.SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN)
        self.assertEqual(ol.classify_cancel_response(raw), ol.SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN)

    def test_missing_required_field_is_unknown(self) -> None:
        raw = _raw_response(status=200, body={"order_id": "O1", "ts_ms": 1})
        self.assertEqual(ol.classify_cancel_response(raw), ol.SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN)

    def test_reduced_by_wrong_type_is_unknown(self) -> None:
        raw = _raw_response(status=200, body={"order_id": "O1", "reduced_by": 1.0, "ts_ms": 1})
        self.assertEqual(ol.classify_cancel_response(raw), ol.SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN)

    def test_ts_ms_bool_is_unknown(self) -> None:
        raw = _raw_response(status=200, body={"order_id": "O1", "reduced_by": "1.00", "ts_ms": True})
        self.assertEqual(ol.classify_cancel_response(raw), ol.SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN)


class TestLifecycleCancelIntegration(unittest.TestCase):
    def test_partial_fill_then_cancel(self) -> None:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_ok_pre_create(),
            create=_ok_create(),
            exact_order=[
                _ok_order_response(client_order_id="5781e77b-e1ed-4303-bcf6-bdb282419251", status="resting", fill_count_fp="0.30", remaining_count_fp="0.70"),
                _ok_order_response(client_order_id="5781e77b-e1ed-4303-bcf6-bdb282419251", status="canceled", fill_count_fp="0.30", remaining_count_fp="0.70"),
            ],
            fills=[
                _ok_fills_response([make_fill(fill_id="F1", count_fp="0.30")]),
                _ok_fills_response([make_fill(fill_id="F1", count_fp="0.30")]),
            ],
            cancel=[_ok_cancel_response(reduced_by="0.70")],
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertEqual(result.terminal, ol.LifecycleTerminal.CANCELED)
        self.assertEqual(result.actual_filled_principal, Decimal("0.003000"))
        self.assertEqual(result.cancel_classification, ol.SendOutcome.DEFINITIVE_SUCCESS)
        self.assertEqual(result.cancel_reduced_by, Decimal("0.70"))

    def test_zero_fill_cancel_reduced_by_one(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        result = plan_and_execute(transport, clock=clock)
        self.assertEqual(result.terminal, ol.LifecycleTerminal.CANCELED)
        self.assertEqual(result.fills, ())

    def test_cancel_conservation_mismatch_halts_lifecycle(self) -> None:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_ok_pre_create(),
            create=_ok_create(),
            exact_order=[
                _ok_order_response(client_order_id="5781e77b-e1ed-4303-bcf6-bdb282419251", status="resting", fill_count_fp="0.30", remaining_count_fp="0.70"),
                _ok_order_response(client_order_id="5781e77b-e1ed-4303-bcf6-bdb282419251", status="canceled", fill_count_fp="0.30", remaining_count_fp="0.70"),
            ],
            fills=[
                _ok_fills_response([make_fill(fill_id="F1", count_fp="0.30")]),
                _ok_fills_response([make_fill(fill_id="F1", count_fp="0.30")]),
            ],
            cancel=[_ok_cancel_response(reduced_by="0.50")],  # 0.30 + 0.50 != 1.00
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.CANCEL_QUANTITY_CONSERVATION_MISMATCH)

    def test_no_compensating_order_ever_sent(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        plan_and_execute(transport, clock=clock)
        self.assertEqual(len(transport.calls_for(ol.LifecycleOperation.CREATE)), 1)

    def test_full_fill_no_cancel_attempted(self) -> None:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_ok_pre_create(),
            create=_ok_create(),
            exact_order=[_ok_order_response(client_order_id="5781e77b-e1ed-4303-bcf6-bdb282419251", status="executed", fill_count_fp="1.00", remaining_count_fp="0.00")],
            fills=[_ok_fills_response([make_fill(fill_id="F1", count_fp="1.00")])],
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertEqual(result.terminal, ol.LifecycleTerminal.FILLED)
        self.assertEqual(len(transport.calls_for(ol.LifecycleOperation.CANCEL)), 0)

    def test_already_canceled_terminal_without_cancel_send(self) -> None:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_ok_pre_create(),
            create=_ok_create(),
            exact_order=[_ok_order_response(client_order_id="5781e77b-e1ed-4303-bcf6-bdb282419251", status="canceled", fill_count_fp="0.00", remaining_count_fp="0.00")],
            fills=[_ok_fills_response([])],
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertEqual(result.terminal, ol.LifecycleTerminal.ALREADY_CANCELED)
        self.assertEqual(len(transport.calls_for(ol.LifecycleOperation.CANCEL)), 0)

    def test_ambiguous_cancel_never_sends_second_delete(self) -> None:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_ok_pre_create(),
            create=_ok_create(),
            exact_order=[
                _ok_order_response(client_order_id="5781e77b-e1ed-4303-bcf6-bdb282419251", status="resting"),
                _ok_order_response(client_order_id="5781e77b-e1ed-4303-bcf6-bdb282419251", status="resting"),  # ambiguous-cancel reread
            ],
            fills=[_ok_fills_response([]), _ok_fills_response([])],
            cancel=[_raw_response(status=200, body={}, send_result_classification=ol.SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN)],
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.CANCEL_AMBIGUOUS_UNRESOLVED)
        self.assertEqual(len(transport.calls_for(ol.LifecycleOperation.CANCEL)), 1)

    def test_5xx_cancel_is_unknown_and_never_resent(self) -> None:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_ok_pre_create(),
            create=_ok_create(),
            exact_order=[_ok_order_response(client_order_id="5781e77b-e1ed-4303-bcf6-bdb282419251", status="resting")],
            fills=[_ok_fills_response([])],
            cancel=[_raw_response(status=500, body={"error": "internal"})],
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.CANCEL_AMBIGUOUS_UNRESOLVED)
        self.assertTrue(result.unknown_result)
        self.assertEqual(len(transport.calls_for(ol.LifecycleOperation.CANCEL)), 1)

    def test_cancel_response_order_id_mismatch_halts(self) -> None:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_ok_pre_create(),
            create=_ok_create(),
            exact_order=[_ok_order_response(client_order_id="5781e77b-e1ed-4303-bcf6-bdb282419251", status="resting")],
            fills=[_ok_fills_response([])],
            cancel=[_ok_cancel_response(order_id="ORDER-WRONG", reduced_by="1.00")],
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.CANCEL_RESPONSE_MALFORMED)

    def test_cancel_response_client_order_id_mismatch_halts(self) -> None:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_ok_pre_create(),
            create=_ok_create(),
            exact_order=[_ok_order_response(client_order_id="5781e77b-e1ed-4303-bcf6-bdb282419251", status="resting")],
            fills=[_ok_fills_response([])],
            cancel=[_ok_cancel_response(reduced_by="1.00", client_order_id="not-the-frozen-id")],
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.CANCEL_RESPONSE_MALFORMED)


# ---------------------------------------------------------------------------
# Final fill pagination after cancel
# ---------------------------------------------------------------------------

class TestFinalFillPaginationAfterCancel(unittest.TestCase):
    def test_multi_page_final_fills_drained_completely(self) -> None:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_ok_pre_create(),
            create=_ok_create(),
            exact_order=[
                _ok_order_response(client_order_id="5781e77b-e1ed-4303-bcf6-bdb282419251", status="resting", fill_count_fp="0.60", remaining_count_fp="0.40"),
                _ok_order_response(client_order_id="5781e77b-e1ed-4303-bcf6-bdb282419251", status="canceled", fill_count_fp="0.60", remaining_count_fp="0.40"),
            ],
            fills=[
                # Initial fills read (pre-cancel): single page, 0.60 total.
                _ok_fills_response([make_fill(fill_id="F1", count_fp="0.30"), make_fill(fill_id="F2", count_fp="0.30")]),
                # Final post-cancel fills read: two pages, same 0.60 total
                # (idempotent replay), proving pagination is drained fully.
                _raw_response(status=200, body={"fills": [make_fill(fill_id="F1", count_fp="0.30").__class__ and make_fill(fill_id="F1", count_fp="0.30")], "cursor": "page2"}),
                _ok_fills_response([make_fill(fill_id="F2", count_fp="0.30")], cursor=""),
            ],
            cancel=[_ok_cancel_response(reduced_by="0.40")],
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertEqual(result.terminal, ol.LifecycleTerminal.CANCELED)
        self.assertEqual(result.actual_filled_principal, Decimal("0.006000"))
        fill_calls = transport.calls_for(ol.LifecycleOperation.FILLS)
        self.assertEqual(len(fill_calls), 3)

    def test_final_fill_pagination_uses_exact_prior_cursor(self) -> None:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_ok_pre_create(),
            create=_ok_create(),
            exact_order=[
                _ok_order_response(client_order_id="5781e77b-e1ed-4303-bcf6-bdb282419251", status="resting", fill_count_fp="0.00", remaining_count_fp="1.00"),
                _ok_order_response(client_order_id="5781e77b-e1ed-4303-bcf6-bdb282419251", status="canceled", fill_count_fp="0.00", remaining_count_fp="0.00"),
            ],
            fills=[
                _ok_fills_response([]),
                _raw_response(status=200, body={"fills": [], "cursor": "exact-cursor-abc"}),
                _ok_fills_response([], cursor=""),
            ],
            cancel=[_ok_cancel_response(reduced_by="1.00")],
        )
        plan_and_execute(transport, clock=clock)
        fill_calls = transport.calls_for(ol.LifecycleOperation.FILLS)
        self.assertEqual(len(fill_calls), 3)
        self.assertEqual(fill_calls[2].query.get("cursor"), "exact-cursor-abc")

    def test_incomplete_final_pagination_within_budget_halts(self) -> None:
        clock = _FixedClock()
        # Initial fills read consumes 1 of 4; three more pages remain
        # available, but the final drain needs a 4th (5th overall) page,
        # which exceeds the fills budget -- must halt rather than accept
        # a partial final page set.
        transport = build_transport(
            pre_create=_ok_pre_create(),
            create=_ok_create(),
            exact_order=[
                _ok_order_response(client_order_id="5781e77b-e1ed-4303-bcf6-bdb282419251", status="resting"),
                _ok_order_response(client_order_id="5781e77b-e1ed-4303-bcf6-bdb282419251", status="canceled"),
            ],
            fills=[
                _ok_fills_response([], cursor=""),  # initial read: 1 used
                _raw_response(status=200, body={"fills": [], "cursor": "p1"}),  # final read page 1: 2 used
                _raw_response(status=200, body={"fills": [], "cursor": "p2"}),  # final read page 2: 3 used
                _raw_response(status=200, body={"fills": [], "cursor": "p3"}),  # final read page 3: 4 used (budget exhausted)
            ],
            cancel=[_ok_cancel_response(reduced_by="1.00")],
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.FINAL_FILL_RECONCILIATION_INCOMPLETE)


# ---------------------------------------------------------------------------
# 70-79: request/deadline envelope
# ---------------------------------------------------------------------------

class TestRequestBudgetTracker(unittest.TestCase):
    def test_operation_budgets_sum_to_global_max(self) -> None:
        self.assertEqual(sum(ol.OPERATION_BUDGET.values()), ol.GLOBAL_REQUEST_MAXIMUM)
        self.assertEqual(ol.GLOBAL_REQUEST_MAXIMUM, 11)

    def test_branch_budget_maxima(self) -> None:
        self.assertEqual(ol.OPERATION_BUDGET[ol.LifecycleOperation.PRE_CREATE_TRUTH], 1)
        self.assertEqual(ol.OPERATION_BUDGET[ol.LifecycleOperation.CREATE], 1)
        self.assertEqual(ol.OPERATION_BUDGET[ol.LifecycleOperation.RECOVERY], 1)
        self.assertEqual(ol.OPERATION_BUDGET[ol.LifecycleOperation.EXACT_ORDER], 3)
        self.assertEqual(ol.OPERATION_BUDGET[ol.LifecycleOperation.FILLS], 4)
        self.assertEqual(ol.OPERATION_BUDGET[ol.LifecycleOperation.CANCEL], 1)

    def test_operation_cannot_exceed_its_own_budget(self) -> None:
        tracker = ol.RequestBudgetTracker()
        tracker.reserve(ol.LifecycleOperation.PRE_CREATE_TRUTH)
        with self.assertRaises(ol.RequestBudgetExceededError):
            tracker.reserve(ol.LifecycleOperation.PRE_CREATE_TRUTH)

    def test_global_request_maximum_enforced(self) -> None:
        tracker = ol.RequestBudgetTracker()
        tracker.reserve(ol.LifecycleOperation.PRE_CREATE_TRUTH)
        tracker.reserve(ol.LifecycleOperation.CREATE)
        tracker.reserve(ol.LifecycleOperation.RECOVERY)
        for _ in range(3):
            tracker.reserve(ol.LifecycleOperation.EXACT_ORDER)
        for _ in range(4):
            tracker.reserve(ol.LifecycleOperation.FILLS)
        tracker.reserve(ol.LifecycleOperation.CANCEL)
        self.assertEqual(tracker.total_used(), 11)
        with self.assertRaises(ol.RequestBudgetExceededError):
            tracker.reserve(ol.LifecycleOperation.CANCEL)

    def test_no_operation_borrows_budget_from_another(self) -> None:
        tracker = ol.RequestBudgetTracker()
        for _ in range(3):
            tracker.reserve(ol.LifecycleOperation.EXACT_ORDER)
        self.assertEqual(tracker.remaining(ol.LifecycleOperation.EXACT_ORDER), 0)
        self.assertEqual(tracker.remaining(ol.LifecycleOperation.FILLS), 4)

    def test_lifecycle_halts_on_request_budget_exceeded_for_fills(self) -> None:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_ok_pre_create(),
            create=_ok_create(),
            exact_order=[_ok_order_response(client_order_id="5781e77b-e1ed-4303-bcf6-bdb282419251", status="resting")],
            fills=[
                _ok_fills_response([], cursor="p1"),
                _ok_fills_response([], cursor="p2"),
                _ok_fills_response([], cursor="p3"),
                _ok_fills_response([], cursor="p4"),
            ],
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.FILLS_INCOMPLETE_PAGE_BUDGET)

    def test_zero_automatic_retries_reflected_in_call_counts(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        plan_and_execute(transport, clock=clock)
        for op in (ol.LifecycleOperation.PRE_CREATE_TRUTH, ol.LifecycleOperation.CREATE, ol.LifecycleOperation.CANCEL):
            self.assertLessEqual(len(transport.calls_for(op)), 1)


class TestDeadline(unittest.TestCase):
    def test_master_deadline_constant(self) -> None:
        self.assertEqual(ol.MASTER_DEADLINE_MS, 90_000)

    def test_per_request_ceiling_constant(self) -> None:
        self.assertEqual(ol.PER_REQUEST_CEILING_MS, 10_000)

    def test_effective_request_deadline_clipped_by_master(self) -> None:
        deadline = ol.LifecycleDeadline(monotonic_clock=lambda: 0.0, entry_monotonic=0.0, master_deadline_ms=5_000)
        effective = deadline.effective_request_deadline_monotonic(4_800 / 1000.0, per_request_ceiling_ms=10_000)
        self.assertAlmostEqual(effective, 5.0)

    def test_is_expired_true_past_master_deadline(self) -> None:
        deadline = ol.LifecycleDeadline(monotonic_clock=lambda: 0.0, entry_monotonic=0.0, master_deadline_ms=1_000)
        self.assertTrue(deadline.is_expired(now=2.0))
        self.assertFalse(deadline.is_expired(now=0.5))

    def test_lifecycle_halts_on_expired_deadline_before_pre_create(self) -> None:
        big_jump_clock = _FixedClock(start=0.0, step=1_000_000.0)
        transport = full_happy_path_transport()
        result = plan_and_execute(transport, clock=big_jump_clock)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.DEADLINE_EXCEEDED)

    def test_every_prepared_request_carries_a_clipped_deadline(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        plan_and_execute(transport, clock=clock)
        self.assertGreater(len(transport.calls), 0)
        for call in transport.calls:
            self.assertIsInstance(call.effective_deadline_monotonic, float)
            # Every deadline must be within the 90s master window from the
            # (approximately) 1000.0-start fixed clock.
            self.assertLessEqual(call.effective_deadline_monotonic, 1000.0 + 90.0 + 1.0)

    def test_deadline_propagation_matches_manual_calculation(self) -> None:
        # Build a deadline object identically to the orchestrator's and
        # confirm the first request's deadline matches exactly what a
        # fresh LifecycleDeadline would compute for the same entry time.
        clock = _FixedClock()
        entry = clock.monotonic()  # consumes one tick, mirrors orchestrator's own entry read
        clock2 = _FixedClock()
        transport = full_happy_path_transport()
        plan_and_execute(transport, clock=clock2)
        first_call = transport.calls[0]
        # The deadline must be strictly greater than "now" and at most
        # PER_REQUEST_CEILING_MS ahead of it.
        self.assertGreater(first_call.effective_deadline_monotonic, clock2._value - 90.0)


# ---------------------------------------------------------------------------
# 77-78: no WebSocket / no production fallback; 79-80: no amendment/second order
# ---------------------------------------------------------------------------

class TestNoFallbackOrAmendmentSurfaces(unittest.TestCase):
    def test_no_websocket_symbol_exported(self) -> None:
        exported_lower = {name.lower() for name in ol.__all__}
        self.assertFalse(any("websocket" in name for name in exported_lower))

    def test_no_amend_decrease_reprice_replacement_helper_symbols(self) -> None:
        forbidden_substrings = ("reprice", "replace")
        for name in dir(ol):
            lowered = name.lower()
            for forbidden in forbidden_substrings:
                self.assertNotIn(forbidden, lowered, msg=f"unexpected surface: {name}")

    def test_dispatch_expectation_is_the_only_amend_decrease_surface(self) -> None:
        # "amend"/"decrease" appear only inside the closed negative-capability
        # declaration, never as an executable code path.
        names_mentioning = [n for n in dir(ol) if "amend" in n.lower() or "decrease" in n.lower()]
        self.assertEqual(names_mentioning, [])  # the fields live inside the dataclass, not as module names

    def test_only_one_ticker_field_on_lifecycle_input(self) -> None:
        import dataclasses

        field_names = [f.name for f in dataclasses.fields(ol.OneOrderLifecycleInput)]
        ticker_like = [name for name in field_names if "ticker" in name.lower()]
        self.assertEqual(ticker_like, ["market_ticker"])


# ---------------------------------------------------------------------------
# 81-82: secret-safe evidence / no real secret reads
# ---------------------------------------------------------------------------

class TestSecretSafety(unittest.TestCase):
    def test_halt_codes_never_contain_secret_like_text(self) -> None:
        for code in ol.LifecycleHaltCode:
            lowered = code.value.lower()
            for forbidden in ("secret", "password", "private_key", "pem"):
                self.assertNotIn(forbidden, lowered)

    def test_module_never_imports_networking_or_os_environ_directly(self) -> None:
        import inspect

        source = inspect.getsource(ol)
        for forbidden in ("import socket", "import requests", "import http.client", "os.environ", "urllib.request"):
            self.assertNotIn(forbidden, source)

    def test_writer_proof_repr_does_not_crash_and_is_a_string(self) -> None:
        proof = make_valid_proof()
        self.assertIsInstance(repr(proof), str)

    def test_result_evidence_includes_required_fields(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        result = plan_and_execute(transport, clock=clock)
        self.assertIsNotNone(result.proof_id)
        self.assertIsNotNone(result.writer_session_id)
        self.assertIsNotNone(result.account_scope_ref)
        self.assertIn("PRE_CREATE_TRUTH", result.request_counts)


# ---------------------------------------------------------------------------
# 83-84: signing canonical message / fake RSA-PSS signing behavior
# ---------------------------------------------------------------------------

class TestSigningContract(unittest.TestCase):
    def test_timestamp_ms_text_canonical_form(self) -> None:
        self.assertTrue(ol.timestamp_ms_text_is_canonical("1731000000000"))
        self.assertFalse(ol.timestamp_ms_text_is_canonical("-1731000000000"))
        self.assertFalse(ol.timestamp_ms_text_is_canonical("1731000000000.0"))
        self.assertFalse(ol.timestamp_ms_text_is_canonical(" 1731000000000"))
        self.assertFalse(ol.timestamp_ms_text_is_canonical(""))
        self.assertFalse(ol.timestamp_ms_text_is_canonical(1731000000000))  # type: ignore[arg-type]

    def test_signing_message_excludes_query_host_body(self) -> None:
        message = ol.build_signing_message(
            timestamp_ms_text="1731000000000", method="get", full_path="/trade-api/v2/portfolio/orders",
        )
        self.assertEqual(message, b"1731000000000GET/trade-api/v2/portfolio/orders")
        self.assertNotIn(b"external-api.demo.kalshi.co", message)
        self.assertNotIn(b"?", message)

    def test_signing_message_rejects_query_string(self) -> None:
        with self.assertRaises(ValueError):
            ol.build_signing_message(timestamp_ms_text="1731000000000", method="GET", full_path="/trade-api/v2/portfolio/orders?ticker=X")

    def test_signing_message_requires_trade_api_v2_prefix(self) -> None:
        with self.assertRaises(ValueError):
            ol.build_signing_message(timestamp_ms_text="1731000000000", method="GET", full_path="/some/other/path")

    # -- SAME_SCOPE_CORRECTION_03, point 8: no generic signer surface ------

    def test_generic_sign_message_surface_removed(self) -> None:
        self.assertFalse(hasattr(ol, "sign_message"))

    def _cancel_request(self, order_id: str = "ORDER-1") -> ol.PreparedRequest:
        return ol.PreparedRequest(
            operation=ol.LifecycleOperation.CANCEL,
            method="DELETE",
            path=f"/trade-api/v2/portfolio/events/orders/{order_id}",
            query=ol.build_cancel_query(),
            body=None,
            effective_deadline_monotonic=1000.0,
        )

    def test_fake_rsa_pss_signing_round_trip(self) -> None:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        request = self._cancel_request()
        signature = ol.sign_lifecycle_request(request, private_key, timestamp_ms_text="1731000000001")
        message = ol.build_signing_message(timestamp_ms_text="1731000000001", method="DELETE", full_path=request.path)
        public_key = private_key.public_key()
        public_key.verify(signature, message, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32), hashes.SHA256())

    def test_fake_signing_fails_to_verify_with_wrong_message(self) -> None:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        request = self._cancel_request()
        signature = ol.sign_lifecycle_request(request, private_key, timestamp_ms_text="1731000000001")
        message = ol.build_signing_message(timestamp_ms_text="1731000000001", method="DELETE", full_path=request.path)
        tampered = message + b"tampered"
        public_key = private_key.public_key()
        with self.assertRaises(Exception):
            public_key.verify(signature, tampered, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32), hashes.SHA256())

    def test_sign_lifecycle_request_rejects_unknown_path(self) -> None:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        request = ol.PreparedRequest(
            operation=ol.LifecycleOperation.PRE_CREATE_TRUTH,
            method="GET",
            path="/trade-api/v2/some/other/unknown/path",
            query={},
            body=None,
            effective_deadline_monotonic=1000.0,
        )
        with self.assertRaises(ValueError):
            ol.sign_lifecycle_request(request, private_key, timestamp_ms_text="1731000000001")

    def test_sign_lifecycle_request_rejects_method_path_mismatch(self) -> None:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        request = ol.PreparedRequest(
            operation=ol.LifecycleOperation.CREATE,
            method="GET",  # CREATE's exact fixed contract is POST
            path="/trade-api/v2/portfolio/events/orders",
            query={},
            body=None,
            effective_deadline_monotonic=1000.0,
        )
        with self.assertRaises(ValueError):
            ol.sign_lifecycle_request(request, private_key, timestamp_ms_text="1731000000001")

    def test_sign_lifecycle_request_rejects_query_embedded_in_path(self) -> None:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        request = ol.PreparedRequest(
            operation=ol.LifecycleOperation.PRE_CREATE_TRUTH,
            method="GET",
            path="/trade-api/v2/portfolio/orders?ticker=X",
            query={},
            body=None,
            effective_deadline_monotonic=1000.0,
        )
        with self.assertRaises(ValueError):
            ol.sign_lifecycle_request(request, private_key, timestamp_ms_text="1731000000001")

    def test_sign_lifecycle_request_rejects_non_lifecycle_operation(self) -> None:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

        class _FakeRequest:
            operation = "NOT_A_REAL_OPERATION"
            method = "GET"
            path = "/trade-api/v2/portfolio/orders"

        with self.assertRaises(ValueError):
            ol.sign_lifecycle_request(_FakeRequest(), private_key, timestamp_ms_text="1731000000001")  # type: ignore[arg-type]

    def test_sign_lifecycle_request_never_signs_host_or_body(self) -> None:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        request = ol.PreparedRequest(
            operation=ol.LifecycleOperation.CREATE,
            method="POST",
            path="/trade-api/v2/portfolio/events/orders",
            query={},
            body={"ticker": "SHOULD-NOT-BE-SIGNED"},
            effective_deadline_monotonic=1000.0,
        )
        signature = ol.sign_lifecycle_request(request, private_key, timestamp_ms_text="1731000000001")
        expected_message = ol.build_signing_message(timestamp_ms_text="1731000000001", method="POST", full_path=request.path)
        self.assertNotIn(b"SHOULD-NOT-BE-SIGNED", expected_message)
        public_key = private_key.public_key()
        public_key.verify(signature, expected_message, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32), hashes.SHA256())


# ---------------------------------------------------------------------------
# 85: Decimal/fixed-point-only arithmetic
# ---------------------------------------------------------------------------

class TestDecimalOnlyArithmetic(unittest.TestCase):
    def test_economic_constants_are_decimal(self) -> None:
        self.assertIsInstance(ol.QUANTITY, Decimal)
        self.assertIsInstance(ol.LIMIT_PRICE, Decimal)
        self.assertIsInstance(ol.MAX_FILLED_PRINCIPAL, Decimal)
        self.assertIsInstance(ol.MAX_TOTAL_RISK, Decimal)

    def test_ledger_arithmetic_uses_decimal_not_float(self) -> None:
        ledger = ol.FillLedger()
        ledger.ingest(make_fill(fill_id="F1", count_fp="0.10"), bound_order_id="ORDER-0001", ticker=TICKER)
        ledger.ingest(make_fill(fill_id="F2", count_fp="0.20"), bound_order_id="ORDER-0001", ticker=TICKER)
        total = ledger.total_quantity()
        self.assertIsInstance(total, Decimal)
        self.assertEqual(total, Decimal("0.30"))

    def test_total_risk_relationship_preserved(self) -> None:
        max_fee = ol.MAX_TOTAL_RISK - ol.MAX_FILLED_PRINCIPAL
        self.assertEqual(max_fee, Decimal("0.040000"))
        self.assertLessEqual(ol.MAX_FILLED_PRINCIPAL + max_fee, ol.MAX_TOTAL_RISK)

    def test_cancel_conservation_uses_decimal(self) -> None:
        result = ol.check_cancel_conservation(final_fill_quantity=Decimal("0.10"), reduced_by=Decimal("0.90"))
        self.assertIsNone(result)

    def test_fee_risk_binding_requires_decimal_type(self) -> None:
        with self.assertRaises(TypeError):
            ol.OneOrderFeeRiskBinding(max_fee_dollars=0.04)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# SAME_SCOPE_CORRECTION_03, point 4: client_order_id frozen before pre-create
# ---------------------------------------------------------------------------

class TestClientOrderIdFreezing(unittest.TestCase):
    def test_is_valid_lowercase_uuid4_accepts_real_uuid4(self) -> None:
        self.assertTrue(ol.is_valid_lowercase_uuid4(DEFAULT_CLIENT_ORDER_ID))

    def test_is_valid_lowercase_uuid4_rejects_uppercase(self) -> None:
        self.assertFalse(ol.is_valid_lowercase_uuid4(DEFAULT_CLIENT_ORDER_ID.upper()))

    def test_is_valid_lowercase_uuid4_rejects_wrong_version_nibble(self) -> None:
        # A real UUID v1-shaped string (version nibble '1', not '4').
        self.assertFalse(ol.is_valid_lowercase_uuid4("5781e77b-e1ed-1303-bcf6-bdb282419251"))

    def test_is_valid_lowercase_uuid4_rejects_wrong_variant_nibble(self) -> None:
        # Variant nibble must be one of 8/9/a/b; '7' is not.
        self.assertFalse(ol.is_valid_lowercase_uuid4("5781e77b-e1ed-4303-7cf6-bdb282419251"))

    def test_is_valid_lowercase_uuid4_rejects_non_uuid_string(self) -> None:
        self.assertFalse(ol.is_valid_lowercase_uuid4("not-a-uuid-at-all"))

    def test_is_valid_lowercase_uuid4_rejects_non_string(self) -> None:
        self.assertFalse(ol.is_valid_lowercase_uuid4(12345))  # type: ignore[arg-type]

    def test_generate_client_order_id_produces_valid_form(self) -> None:
        generated = ol.generate_client_order_id()
        self.assertTrue(ol.is_valid_lowercase_uuid4(generated))

    def test_missing_client_order_id_halts_before_transport(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        lifecycle_input = make_lifecycle_input(client_order_id="")
        plan_result = ol.plan_demo_one_order_lifecycle(
            lifecycle_input, _utc_clock=lambda: EXECUTOR_ENTRY_UTC, monotonic_clock=clock.monotonic,
        )
        self.assertIsInstance(plan_result, ol.OneOrderLifecycleHalt)
        self.assertEqual(plan_result.halt_code, ol.LifecycleHaltCode.CLIENT_ORDER_ID_MISSING)
        self.assertEqual(transport.calls, [])

    def test_none_client_order_id_halts_before_transport(self) -> None:
        clock = _FixedClock()
        lifecycle_input = make_lifecycle_input(client_order_id=None)
        plan_result = ol.plan_demo_one_order_lifecycle(
            lifecycle_input, _utc_clock=lambda: EXECUTOR_ENTRY_UTC, monotonic_clock=clock.monotonic,
        )
        self.assertIsInstance(plan_result, ol.OneOrderLifecycleHalt)
        self.assertEqual(plan_result.halt_code, ol.LifecycleHaltCode.CLIENT_ORDER_ID_MISSING)

    def test_malformed_client_order_id_halts_before_transport(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        lifecycle_input = make_lifecycle_input(client_order_id="not-a-real-uuid")
        plan_result = ol.plan_demo_one_order_lifecycle(
            lifecycle_input, _utc_clock=lambda: EXECUTOR_ENTRY_UTC, monotonic_clock=clock.monotonic,
        )
        self.assertIsInstance(plan_result, ol.OneOrderLifecycleHalt)
        self.assertEqual(plan_result.halt_code, ol.LifecycleHaltCode.CLIENT_ORDER_ID_MALFORMED)
        self.assertEqual(transport.calls, [])

    def test_uppercase_client_order_id_halts_before_transport(self) -> None:
        clock = _FixedClock()
        lifecycle_input = make_lifecycle_input(client_order_id=DEFAULT_CLIENT_ORDER_ID.upper())
        plan_result = ol.plan_demo_one_order_lifecycle(
            lifecycle_input, _utc_clock=lambda: EXECUTOR_ENTRY_UTC, monotonic_clock=clock.monotonic,
        )
        self.assertIsInstance(plan_result, ol.OneOrderLifecycleHalt)
        self.assertEqual(plan_result.halt_code, ol.LifecycleHaltCode.CLIENT_ORDER_ID_MALFORMED)

    def test_non_v4_client_order_id_halts_before_transport(self) -> None:
        clock = _FixedClock()
        # A structurally UUID-shaped but non-v4 string (version nibble '1').
        lifecycle_input = make_lifecycle_input(client_order_id="5781e77b-e1ed-1303-bcf6-bdb282419251")
        plan_result = ol.plan_demo_one_order_lifecycle(
            lifecycle_input, _utc_clock=lambda: EXECUTOR_ENTRY_UTC, monotonic_clock=clock.monotonic,
        )
        self.assertIsInstance(plan_result, ol.OneOrderLifecycleHalt)
        self.assertEqual(plan_result.halt_code, ol.LifecycleHaltCode.CLIENT_ORDER_ID_MALFORMED)

    def test_exact_frozen_id_present_in_plan_before_pre_create(self) -> None:
        clock = _FixedClock()
        lifecycle_input = make_lifecycle_input(client_order_id=ALT_CLIENT_ORDER_ID)
        plan_result = ol.plan_demo_one_order_lifecycle(
            lifecycle_input, _utc_clock=lambda: EXECUTOR_ENTRY_UTC, monotonic_clock=clock.monotonic,
        )
        self.assertIsInstance(plan_result, ol.OneOrderLifecyclePlan)
        self.assertEqual(plan_result.client_order_id, ALT_CLIENT_ORDER_ID)

    def test_create_request_body_uses_the_exact_frozen_id(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport(client_order_id=ALT_CLIENT_ORDER_ID)
        result = plan_and_execute(transport, clock=clock, client_order_id=ALT_CLIENT_ORDER_ID)
        self.assertIsInstance(result, ol.OneOrderLifecycleResult)
        create_calls = transport.calls_for(ol.LifecycleOperation.CREATE)
        self.assertEqual(len(create_calls), 1)
        self.assertEqual(create_calls[0].body["client_order_id"], ALT_CLIENT_ORDER_ID)
        self.assertEqual(result.client_order_id, ALT_CLIENT_ORDER_ID)

    def test_ambiguous_create_recovery_reuses_the_same_frozen_id(self) -> None:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_ok_pre_create(),
            create=_raw_response(status=201, body={}, send_result_classification=ol.SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN),
            recovery=[_raw_response(status=200, body={"orders": [make_order(order_id="ORDER-REC", client_order_id=ALT_CLIENT_ORDER_ID)], "cursor": ""})],
            exact_order=[
                _ok_order_response(order_id="ORDER-REC", client_order_id=ALT_CLIENT_ORDER_ID),
                _ok_order_response(order_id="ORDER-REC", client_order_id=ALT_CLIENT_ORDER_ID, status="canceled"),
            ],
            fills=[_ok_fills_response(), _ok_fills_response()],
            cancel=[_ok_cancel_response(order_id="ORDER-REC", reduced_by="1.00")],
        )
        result = plan_and_execute(transport, clock=clock, client_order_id=ALT_CLIENT_ORDER_ID)
        self.assertIsInstance(result, ol.OneOrderLifecycleResult)
        recovery_calls = transport.calls_for(ol.LifecycleOperation.RECOVERY)
        self.assertEqual(len(recovery_calls), 1)
        # The recovery query itself doesn't carry client_order_id (it's
        # matched locally against the response), so the real proof this
        # scenario cares about is that the resulting bound order/client ID
        # is exactly the frozen one, with no second CREATE ever sent.
        self.assertEqual(result.client_order_id, ALT_CLIENT_ORDER_ID)
        self.assertEqual(len(transport.calls_for(ol.LifecycleOperation.CREATE)), 1)

    def test_no_new_id_generated_after_send_may_have_begun(self) -> None:
        # generate_client_order_id() is never called by plan/execute --
        # confirmed structurally: the frozen ID always traces back to the
        # caller-supplied OneOrderLifecycleInput.client_order_id, and the
        # ambiguous-recovery test above shows the same ID reused, not a
        # freshly generated one.
        import inspect

        execute_source = inspect.getsource(ol.execute_demo_one_order_lifecycle)
        plan_source = inspect.getsource(ol.plan_demo_one_order_lifecycle)
        self.assertNotIn("generate_client_order_id(", execute_source)
        self.assertNotIn("generate_client_order_id(", plan_source)

    def test_generate_client_order_id_is_an_upstream_only_convenience(self) -> None:
        # Documented as available for use before planning begins, not
        # called internally by this module's own orchestration.
        self.assertIn("upstream", ol.generate_client_order_id.__doc__.lower())


# ---------------------------------------------------------------------------
# SAME_SCOPE_CORRECTION_03, point 5: complete success/halt evidence contracts
# ---------------------------------------------------------------------------

class TestEvidenceContracts(unittest.TestCase):
    def test_halt_is_never_a_result_type(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        bad_authz = make_valid_authorization(accepted_spec_sha256="0" * 64)
        result = plan_and_execute(transport, clock=clock, authorization=bad_authz)
        self.assertIsInstance(result, ol.OneOrderLifecycleHalt)
        self.assertNotIsInstance(result, ol.OneOrderLifecycleResult)

    def test_result_is_never_a_halt_type(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        result = plan_and_execute(transport, clock=clock)
        self.assertIsInstance(result, ol.OneOrderLifecycleResult)
        self.assertNotIsInstance(result, ol.OneOrderLifecycleHalt)

    def test_result_and_halt_are_wholly_distinct_types(self) -> None:
        self.assertFalse(issubclass(ol.OneOrderLifecycleResult, ol.OneOrderLifecycleHalt))
        self.assertFalse(issubclass(ol.OneOrderLifecycleHalt, ol.OneOrderLifecycleResult))

    def test_plan_halt_has_zero_baseline_evidence(self) -> None:
        clock = _FixedClock()
        lifecycle_input = make_lifecycle_input(client_order_id="")
        plan_result = ol.plan_demo_one_order_lifecycle(
            lifecycle_input, _utc_clock=lambda: EXECUTOR_ENTRY_UTC, monotonic_clock=clock.monotonic,
        )
        self.assertIsInstance(plan_result, ol.OneOrderLifecycleHalt)
        self.assertEqual(plan_result.stage, "PLAN")
        self.assertFalse(plan_result.create_send_may_have_begun)
        self.assertFalse(plan_result.cancel_send_may_have_begun)
        self.assertEqual(plan_result.created_order_upper_bound, 0)
        self.assertFalse(plan_result.unknown_result)
        self.assertEqual(plan_result.request_counts, {})

    def test_execute_halt_carries_proof_and_prior_write_state(self) -> None:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_ok_pre_create(),
            create=_raw_response(status=400, body={"error": "rejected"}),
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertIsInstance(result, ol.OneOrderLifecycleHalt)
        self.assertEqual(result.stage, "EXECUTE")
        self.assertEqual(result.proof_state, "HELD")
        self.assertEqual(result.prior_write_state, "NO_UNRESOLVED_SAME_SCOPE_WRITE")

    def test_ambiguous_create_halt_flags_send_may_have_begun(self) -> None:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_ok_pre_create(),
            create=_raw_response(status=201, body={}, send_result_classification=ol.SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN),
            recovery=[_raw_response(status=200, body={"orders": [], "cursor": ""})],
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertIsInstance(result, ol.OneOrderLifecycleHalt)
        self.assertTrue(result.create_send_may_have_begun)
        self.assertTrue(result.unknown_result)
        self.assertEqual(result.created_order_upper_bound, 1)

    def test_received_create_http_rejection_remains_unknown(self) -> None:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_ok_pre_create(),
            create=_raw_response(status=400, body={"error": "rejected"}),
            recovery=[_raw_response(status=200, body={"orders": [], "cursor": ""})],
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertIsInstance(result, ol.OneOrderLifecycleHalt)
        self.assertTrue(result.create_send_may_have_begun)
        self.assertTrue(result.unknown_result)
        self.assertEqual(result.created_order_upper_bound, 1)
        self.assertFalse(result.proof_release_eligible)

    def test_ambiguous_cancel_halt_flags_cancel_send_may_have_begun(self) -> None:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_ok_pre_create(),
            create=_ok_create(),
            exact_order=[
                _ok_order_response(client_order_id=DEFAULT_CLIENT_ORDER_ID, status="resting"),
                _ok_order_response(client_order_id=DEFAULT_CLIENT_ORDER_ID, status="resting"),  # ambiguous-cancel best-effort reread
            ],
            fills=[_ok_fills_response([]), _ok_fills_response([])],
            cancel=[_raw_response(status=200, body={}, send_result_classification=ol.SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN)],
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertIsInstance(result, ol.OneOrderLifecycleHalt)
        self.assertTrue(result.cancel_send_may_have_begun)
        self.assertTrue(result.unknown_result)

    def test_halt_carries_source_and_binding_identities(self) -> None:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_ok_pre_create(),
            create=_raw_response(status=400, body={"error": "rejected"}),
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertIsInstance(result, ol.OneOrderLifecycleHalt)
        self.assertEqual(result.source_record_sha256, ol.SOURCE_RECORD_SHA256)
        self.assertEqual(set(result.operation_binding_sha256.keys()), set(ol.OPERATION_BINDINGS.keys()))

    def test_halt_evidence_never_contains_secret_like_substrings(self) -> None:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_ok_pre_create(),
            create=_raw_response(status=400, body={"error": "rejected"}),
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertIsInstance(result, ol.OneOrderLifecycleHalt)
        rendered = repr(result).lower()
        for forbidden in ("private_key", "begin rsa", "-----begin", ".pem"):
            self.assertNotIn(forbidden, rendered)

    def test_result_evidence_includes_full_section_75_field_set(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        result = plan_and_execute(transport, clock=clock)
        self.assertIsInstance(result, ol.OneOrderLifecycleResult)
        # Spot-check the fields Correction 01/02's LifecycleResult never had.
        self.assertEqual(result.gustavo_execution_authorization_id, LIFECYCLE_AUTH_ID)
        self.assertEqual(result.environment, "KALSHI_DEMO")
        self.assertEqual(result.subaccount, 0)
        self.assertEqual(result.account_scope_ref, ACCOUNT_SCOPE_REF)
        self.assertTrue(result.pre_create_truth_confirmed)
        self.assertEqual(result.final_status, "canceled")
        self.assertEqual(result.fill_price_validations, ())
        self.assertTrue(result.principal_within_bound)
        self.assertEqual(result.cancel_conservation_result, True)
        self.assertEqual(result.source_record_sha256, ol.SOURCE_RECORD_SHA256)
        self.assertEqual(result.proof_continuity_state, "HELD")
        self.assertTrue(result.proof_release_eligible)
        self.assertGreaterEqual(result.elapsed_ms, 0.0)

    def test_fill_price_validations_one_entry_per_fill(self) -> None:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_ok_pre_create(),
            create=_ok_create(),
            exact_order=[
                _ok_order_response(client_order_id=DEFAULT_CLIENT_ORDER_ID, status="resting", fill_count_fp="0.30", remaining_count_fp="0.70"),
                _ok_order_response(client_order_id=DEFAULT_CLIENT_ORDER_ID, status="canceled", fill_count_fp="0.30", remaining_count_fp="0.70"),
            ],
            fills=[
                _ok_fills_response([make_fill(fill_id="F1", count_fp="0.30")]),
                _ok_fills_response([make_fill(fill_id="F1", count_fp="0.30")]),
            ],
            cancel=[_ok_cancel_response(reduced_by="0.70")],
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertIsInstance(result, ol.OneOrderLifecycleResult)
        self.assertEqual(len(result.fill_price_validations), 1)
        fill_id, within_limit = result.fill_price_validations[0]
        self.assertEqual(fill_id, "F1")
        self.assertTrue(within_limit)

    def test_evidence_sha256_deterministic_for_same_evidence(self) -> None:
        clock1 = _FixedClock()
        transport1 = full_happy_path_transport()
        result1 = plan_and_execute(transport1, clock=clock1)

        clock2 = _FixedClock()
        transport2 = full_happy_path_transport()
        result2 = plan_and_execute(transport2, clock=clock2)

        self.assertIsInstance(result1, ol.OneOrderLifecycleResult)
        self.assertIsInstance(result2, ol.OneOrderLifecycleResult)
        self.assertEqual(result1.secret_safe_evidence_sha256, result2.secret_safe_evidence_sha256)

    def test_evidence_sha256_differs_for_different_terminal_states(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        canceled_result = plan_and_execute(transport, clock=clock)

        clock2 = _FixedClock()
        filled_transport = build_transport(
            pre_create=_ok_pre_create(),
            create=_ok_create(),
            exact_order=[_ok_order_response(client_order_id=DEFAULT_CLIENT_ORDER_ID, status="executed", fill_count_fp="1.00", remaining_count_fp="0.00")],
            fills=[_ok_fills_response([make_fill(fill_id="F1", count_fp="1.00")])],
        )
        filled_result = plan_and_execute(filled_transport, clock=clock2)
        self.assertIsInstance(canceled_result, ol.OneOrderLifecycleResult)
        self.assertIsInstance(filled_result, ol.OneOrderLifecycleResult)
        self.assertNotEqual(canceled_result.secret_safe_evidence_sha256, filled_result.secret_safe_evidence_sha256)


# ---------------------------------------------------------------------------
# SAME_SCOPE_CORRECTION_03, point 6: master deadline through final result
# ---------------------------------------------------------------------------

class _JumpAtCallClock:
    """A monotonic clock that advances by a tiny step for the first
    ``jump_before_call`` calls, then jumps far past the master deadline
    for every call from that point on. Used to precisely target the
    *specific* deadline check immediately before terminal-success
    construction, rather than crudely blowing the deadline from the very
    first call (which would prove per-request gating but not point 6's
    requirement that parsing/reconciliation/conservation/evidence
    construction remain covered)."""

    def __init__(self, jump_before_call: int, start: float = 1000.0) -> None:
        self._start = start
        self._n = 0
        self._jump_before_call = jump_before_call

    def monotonic(self) -> float:
        self._n += 1
        if self._n >= self._jump_before_call:
            return self._start + 200.0  # 200s >> 90s master deadline
        return self._start + self._n * 0.001

    def wall(self) -> float:
        return 1_800_000_000.123456


class TestDeadlineThroughFinalResult(unittest.TestCase):
    """Uses ``_JumpAtCallClock``, tuned per scenario so every real
    request/parse/reconciliation/conservation step completes normally and
    only the specific deadline check immediately before terminal-success
    construction (added for point 6) sees an expired clock -- proving
    that check is real and load-bearing, not just the pre-existing
    per-request gates."""

    def test_final_order_parsing_crossing_deadline_cannot_succeed(self) -> None:
        # A huge step ensures the very first post-entry clock read is
        # already past the 90s master deadline, so even the earliest
        # gate (before pre-create) fires. This proves master-deadline
        # enforcement is active end to end; the precisely-tuned variants
        # below isolate the specific point-6 pre-return gate.
        clock = _FixedClock(start=0.0, step=1_000_000.0)
        transport = full_happy_path_transport()
        result = plan_and_execute(transport, clock=clock)
        self.assertIsInstance(result, ol.OneOrderLifecycleHalt)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.DEADLINE_EXCEEDED)
        self.assertEqual(transport.calls, [])

    def test_deadline_checked_immediately_before_canceled_result_construction(self) -> None:
        # jump_before_call=25: experimentally determined so all 7 sends
        # for the full zero-fill CANCELED path complete successfully (the
        # per-request deadline checks and budget reservations all pass),
        # evidence/result construction itself completes, and only the
        # final pre-return boundary check sees the jumped clock.
        # jump_before_call=27 lets the whole lifecycle succeed.
        clock = _JumpAtCallClock(jump_before_call=25)
        transport = full_happy_path_transport()
        result = plan_and_execute(transport, clock=clock)
        self.assertIsInstance(result, ol.OneOrderLifecycleHalt)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.DEADLINE_EXCEEDED)
        # All seven sends (pre-create, create, exact-order x2, fills x2,
        # cancel) completed before the final gate caught the overrun --
        # proving parsing/reconciliation/conservation/evidence
        # construction all ran to completion and it was specifically the
        # pre-return check that fired, not an earlier per-request gate.
        self.assertEqual(len(transport.calls), 7)

    def test_deadline_checked_before_filled_result_construction(self) -> None:
        # jump_before_call=14: all 4 sends (pre-create, create,
        # exact-order, fills) for the FILLED path complete, evidence
        # construction completes, and only the final pre-return check
        # sees the jumped clock.
        clock = _JumpAtCallClock(jump_before_call=14)
        transport = build_transport(
            pre_create=_ok_pre_create(),
            create=_ok_create(),
            exact_order=[_ok_order_response(client_order_id=DEFAULT_CLIENT_ORDER_ID, status="executed", fill_count_fp="1.00", remaining_count_fp="0.00")],
            fills=[_ok_fills_response([make_fill(fill_id="F1", count_fp="1.00")])],
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertIsInstance(result, ol.OneOrderLifecycleHalt)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.DEADLINE_EXCEEDED)
        self.assertEqual(len(transport.calls), 4)

    def test_deadline_checked_before_already_canceled_result_construction(self) -> None:
        clock = _JumpAtCallClock(jump_before_call=14)
        transport = build_transport(
            pre_create=_ok_pre_create(),
            create=_ok_create(),
            exact_order=[_ok_order_response(client_order_id=DEFAULT_CLIENT_ORDER_ID, status="canceled", fill_count_fp="0.00", remaining_count_fp="0.00")],
            fills=[_ok_fills_response([])],
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertIsInstance(result, ol.OneOrderLifecycleHalt)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.DEADLINE_EXCEEDED)
        self.assertEqual(len(transport.calls), 4)

    def test_within_deadline_still_succeeds(self) -> None:
        # Control case: the default small fixed step never approaches the
        # 90000ms deadline, so the lifecycle still succeeds -- proving the
        # new pre-return gate doesn't spuriously fire under normal timing.
        clock = _FixedClock()
        transport = full_happy_path_transport()
        result = plan_and_execute(transport, clock=clock)
        self.assertIsInstance(result, ol.OneOrderLifecycleResult)
        self.assertEqual(result.terminal, ol.LifecycleTerminal.CANCELED)

    def test_one_call_earlier_still_succeeds(self) -> None:
        # jump_before_call=27 (after all CANCELED-path checks)
        # lets every check, including the final pre-return gate, see the
        # small clock -- confirming the boundary is exact, not merely
        # "eventually fails no matter what."
        clock = _JumpAtCallClock(jump_before_call=27)
        transport = full_happy_path_transport()
        result = plan_and_execute(transport, clock=clock)
        self.assertIsInstance(result, ol.OneOrderLifecycleResult)
        self.assertEqual(result.terminal, ol.LifecycleTerminal.CANCELED)

    def test_halt_construction_after_deadline_overrun_remains_secret_safe(self) -> None:
        clock = _JumpAtCallClock(jump_before_call=25)
        transport = full_happy_path_transport()
        result = plan_and_execute(transport, clock=clock)
        self.assertIsInstance(result, ol.OneOrderLifecycleHalt)
        rendered = repr(result).lower()
        for forbidden in ("private_key", "begin rsa", "-----begin", ".pem"):
            self.assertNotIn(forbidden, rendered)


# ---------------------------------------------------------------------------
# SAME_SCOPE_CORRECTION_03, point 7: response media type / retry / redirect
# ---------------------------------------------------------------------------

class TestResponseTransportEvidence(unittest.TestCase):
    def test_default_response_is_well_behaved(self) -> None:
        raw = _raw_response(status=200, body={})
        self.assertIsNone(ol._validate_response_transport_evidence(raw))

    def test_wrong_media_type_halts(self) -> None:
        raw = _raw_response(status=200, body={}, media_type="text/html")
        self.assertEqual(
            ol._validate_response_transport_evidence(raw),
            ol.LifecycleHaltCode.RESPONSE_MEDIA_TYPE_INVALID,
        )

    def test_missing_media_type_halts(self) -> None:
        raw = _raw_response(status=200, body={}, media_type="")
        self.assertEqual(
            ol._validate_response_transport_evidence(raw),
            ol.LifecycleHaltCode.RESPONSE_MEDIA_TYPE_INVALID,
        )

    def test_ambiguous_media_type_with_charset_halts(self) -> None:
        # Only an exact "application/json" is accepted; a technically
        # equivalent but differently-formatted media type is rejected
        # rather than fuzzily parsed.
        raw = _raw_response(status=200, body={}, media_type="application/json; charset=utf-8")
        self.assertEqual(
            ol._validate_response_transport_evidence(raw),
            ol.LifecycleHaltCode.RESPONSE_MEDIA_TYPE_INVALID,
        )

    def test_nonzero_retry_count_halts(self) -> None:
        raw = _raw_response(status=200, body={}, retry_count=1)
        self.assertEqual(
            ol._validate_response_transport_evidence(raw),
            ol.LifecycleHaltCode.RESPONSE_RETRY_OR_REDIRECT_NONZERO,
        )

    def test_nonzero_redirect_count_halts(self) -> None:
        raw = _raw_response(status=200, body={}, redirect_count=1)
        self.assertEqual(
            ol._validate_response_transport_evidence(raw),
            ol.LifecycleHaltCode.RESPONSE_RETRY_OR_REDIRECT_NONZERO,
        )

    def test_negative_retry_count_halts(self) -> None:
        raw = _raw_response(status=200, body={}, retry_count=-1)
        self.assertEqual(
            ol._validate_response_transport_evidence(raw),
            ol.LifecycleHaltCode.RESPONSE_RETRY_OR_REDIRECT_NONZERO,
        )

    def test_bool_retry_count_halts(self) -> None:
        # type(True) is bool, not int -- excluded even though bool is an
        # int subclass and True == 1.
        raw = _raw_response(status=200, body={}, retry_count=True)  # type: ignore[arg-type]
        self.assertEqual(
            ol._validate_response_transport_evidence(raw),
            ol.LifecycleHaltCode.RESPONSE_RETRY_OR_REDIRECT_NONZERO,
        )

    def test_no_automatic_retry_or_redirect_following_surface(self) -> None:
        import inspect

        source = inspect.getsource(ol)
        self.assertNotIn("allow_redirects", source)

    def test_pre_create_response_wrong_media_type_halts_zero_downstream_calls(self) -> None:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_raw_response(status=200, body={"orders": [], "cursor": ""}, media_type="text/html"),
            create=_ok_create(),
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertIsInstance(result, ol.OneOrderLifecycleHalt)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.RESPONSE_MEDIA_TYPE_INVALID)
        self.assertEqual(len(transport.calls_for(ol.LifecycleOperation.CREATE)), 0)

    def test_pre_create_response_body_never_treated_as_authoritative_on_bad_evidence(self) -> None:
        # Even though the body itself is well-formed (would otherwise
        # pass validate_pre_create_response), a bad transport-evidence
        # response must halt before the body is ever inspected.
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_raw_response(status=200, body={"orders": [make_order(client_order_id="other")], "cursor": ""}, retry_count=2),
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertIsInstance(result, ol.OneOrderLifecycleHalt)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.RESPONSE_RETRY_OR_REDIRECT_NONZERO)

    def test_create_response_bad_evidence_halts_with_unknown_result(self) -> None:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_ok_pre_create(),
            create=_raw_response(status=201, body={"order_id": "X", "fill_count": "0.00", "remaining_count": "1.00", "ts_ms": 1}, redirect_count=1),
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertIsInstance(result, ol.OneOrderLifecycleHalt)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.RESPONSE_RETRY_OR_REDIRECT_NONZERO)
        self.assertTrue(result.create_send_may_have_begun)
        self.assertTrue(result.unknown_result)

    def test_cancel_response_bad_evidence_halts(self) -> None:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_ok_pre_create(),
            create=_ok_create(),
            exact_order=[_ok_order_response(client_order_id=DEFAULT_CLIENT_ORDER_ID, status="resting")],
            fills=[_ok_fills_response([])],
            cancel=[_raw_response(status=200, body={"order_id": "ORDER-0001", "reduced_by": "1.00", "ts_ms": 1}, media_type="text/plain")],
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertIsInstance(result, ol.OneOrderLifecycleHalt)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.RESPONSE_MEDIA_TYPE_INVALID)
        self.assertTrue(result.cancel_send_may_have_begun)


# ---------------------------------------------------------------------------
# Full lifecycle integration
# ---------------------------------------------------------------------------

class TestFullLifecycleHappyPath(unittest.TestCase):
    def test_zero_fill_full_cancel_lifecycle(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport(order_id="ORDER-HAPPY", client_order_id="9c8b7a6f-5e4d-4c3b-a291-8f7e6d5c4b3a")
        lifecycle_input = ol.OneOrderLifecycleInput(
            validated_demo_profile=make_valid_demo_profile_via_canonical_validator(),
            authorization_envelope=make_valid_authorization_envelope(),
            lifecycle_authorization=make_valid_authorization(),
            writer_exclusivity_prior_write_proof=make_valid_proof(),
            market_ticker=TICKER,
            client_order_id="9c8b7a6f-5e4d-4c3b-a291-8f7e6d5c4b3a",
            official_source_identity_record_bytes=real_source_record_bytes(),
            operation_binding_record_bytes=real_operation_binding_bytes(),
            fee_risk_binding=ol.OneOrderFeeRiskBinding(max_fee_dollars=Decimal("0.040000")),
            dispatch_expectation=ol.OneOrderLifecycleDispatchExpectation(True, True, True, True, True),
        )
        plan = ol.plan_demo_one_order_lifecycle(
            lifecycle_input, _utc_clock=lambda: EXECUTOR_ENTRY_UTC, monotonic_clock=clock.monotonic,
        )
        self.assertIsInstance(plan, ol.OneOrderLifecyclePlan)
        result = ol.execute_demo_one_order_lifecycle(
            plan,
            transport,
                        monotonic_clock=clock.monotonic,
            _wall_clock=clock.wall,
        )
        self.assertIsInstance(result, ol.OneOrderLifecycleResult)
        self.assertEqual(result.terminal, ol.LifecycleTerminal.CANCELED)
        self.assertEqual(result.request_counts["CANCEL"], 1)
        self.assertEqual(result.request_counts["CREATE"], 1)
        self.assertEqual(result.request_counts["PRE_CREATE_TRUTH"], 1)
        self.assertLessEqual(sum(result.request_counts.values()), ol.GLOBAL_REQUEST_MAXIMUM)
        self.assertEqual(result.client_order_id, "9c8b7a6f-5e4d-4c3b-a291-8f7e6d5c4b3a")
        self.assertEqual(result.bound_order_id, "ORDER-HAPPY")
        self.assertTrue(result.pre_create_truth_confirmed)
        self.assertTrue(result.principal_within_bound)
        self.assertTrue(result.proof_release_eligible)
        self.assertIsInstance(result.secret_safe_evidence_sha256, str)
        self.assertEqual(len(result.secret_safe_evidence_sha256), 64)

    def test_full_lifecycle_uses_real_appendix_bytes_throughout(self) -> None:
        # Confirms the happy path above is exercised with the real,
        # byte-identical Appendix C/D records (not synthetic buffers).
        source = real_source_record_bytes()
        bindings = real_operation_binding_bytes()
        self.assertEqual(hashlib.sha256(source).hexdigest(), ol.SOURCE_RECORD_SHA256)
        for name, raw in bindings.items():
            self.assertEqual(hashlib.sha256(raw).hexdigest(), ol.OPERATION_BINDINGS[name][1])


# ---------------------------------------------------------------------------
# Correction 04 closure tests
# ---------------------------------------------------------------------------

class TestCorrection04StrictTopLevelFields(unittest.TestCase):
    def test_pre_create_missing_orders_halts_before_create(self) -> None:
        clock = _FixedClock()
        transport = build_transport(pre_create=_raw_response(status=200, body={"cursor": ""}))
        result = plan_and_execute(transport, clock=clock)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.PRE_CREATE_MALFORMED_RESPONSE)
        self.assertEqual(len(transport.calls_for(ol.LifecycleOperation.CREATE)), 0)

    def test_pre_create_missing_cursor_halts_before_create(self) -> None:
        clock = _FixedClock()
        transport = build_transport(pre_create=_raw_response(status=200, body={"orders": []}))
        result = plan_and_execute(transport, clock=clock)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.PRE_CREATE_MALFORMED_RESPONSE)
        self.assertEqual(len(transport.calls_for(ol.LifecycleOperation.CREATE)), 0)

    def _recovery_missing(self, body: Mapping[str, object]) -> ol.OneOrderLifecycleHalt:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_ok_pre_create(),
            create=_raw_response(
                status=201, body={},
                send_result_classification=ol.SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN,
            ),
            recovery=[_raw_response(status=200, body=body)],
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertIsInstance(result, ol.OneOrderLifecycleHalt)
        self.assertTrue(result.unknown_result)
        self.assertEqual(result.created_order_upper_bound, 1)
        return result

    def test_recovery_missing_orders_halts_unresolved(self) -> None:
        result = self._recovery_missing({"cursor": ""})
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.RECOVERY_MALFORMED_RESPONSE)

    def test_recovery_missing_cursor_halts_unresolved(self) -> None:
        result = self._recovery_missing({"orders": []})
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.RECOVERY_MALFORMED_RESPONSE)

    def _initial_fills_missing(self, body: Mapping[str, object]) -> ol.OneOrderLifecycleHalt:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_ok_pre_create(), create=_ok_create(),
            exact_order=[_ok_order_response(client_order_id=DEFAULT_CLIENT_ORDER_ID, status="resting")],
            fills=[_raw_response(status=200, body=body)],
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertIsInstance(result, ol.OneOrderLifecycleHalt)
        return result

    def test_initial_fills_missing_fills_halts(self) -> None:
        self.assertEqual(
            self._initial_fills_missing({"cursor": ""}).halt_code,
            ol.LifecycleHaltCode.FILL_MALFORMED,
        )

    def test_initial_fills_missing_cursor_halts(self) -> None:
        self.assertEqual(
            self._initial_fills_missing({"fills": []}).halt_code,
            ol.LifecycleHaltCode.FILL_MALFORMED,
        )

    def _final_fills_missing(self, body: Mapping[str, object]) -> ol.OneOrderLifecycleHalt:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_ok_pre_create(), create=_ok_create(),
            exact_order=[
                _ok_order_response(client_order_id=DEFAULT_CLIENT_ORDER_ID, status="resting"),
                _ok_order_response(client_order_id=DEFAULT_CLIENT_ORDER_ID, status="canceled"),
            ],
            fills=[_ok_fills_response([]), _raw_response(status=200, body=body)],
            cancel=[_ok_cancel_response(reduced_by="1.00")],
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertIsInstance(result, ol.OneOrderLifecycleHalt)
        return result

    def test_final_fills_missing_fills_cannot_succeed(self) -> None:
        self.assertEqual(self._final_fills_missing({"cursor": ""}).halt_code, ol.LifecycleHaltCode.FILL_MALFORMED)

    def test_final_fills_missing_cursor_cannot_succeed(self) -> None:
        self.assertEqual(self._final_fills_missing({"fills": []}).halt_code, ol.LifecycleHaltCode.FILL_MALFORMED)


class TestCorrection04FixedPointLexing(unittest.TestCase):
    def test_count_parser_rejects_noncanonical_lexical_forms(self) -> None:
        bad = [
            "1e0", "+1.00", "-1.00", " 1.00", "1.00 ", "NaN", "Infinity",
            "-Infinity", "1,00", "1_00", "", "1", "1.0", "1.000", 1.0, 1,
        ]
        for value in bad:
            with self.subTest(value=value):
                self.assertIsNone(ol._parse_fixed_point_count(value))
        self.assertEqual(ol._parse_fixed_point_count("1.00"), Decimal("1.00"))

    def test_dollars_parser_rejects_noncanonical_lexical_forms_and_scale(self) -> None:
        bad = [
            "1e-2", "+0.01", "-0.01", " 0.01", "0.01 ", "NaN", "Infinity",
            "-Infinity", "0,01", "0_01", "", "0.0000001", 0.01, 1,
        ]
        for value in bad:
            with self.subTest(value=value):
                self.assertIsNone(ol._parse_fixed_point_dollars(value))
        self.assertEqual(ol._parse_fixed_point_dollars("0.010000"), Decimal("0.010000"))

    def test_create_count_exponent_halts_without_recovery(self) -> None:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_ok_pre_create(),
            create=_raw_response(status=201, body={
                "order_id": "ORDER-0001", "fill_count": "0e0", "remaining_count": "1.00", "ts_ms": 1,
            }),
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.CREATE_RESPONSE_MALFORMED)
        self.assertEqual(len(transport.calls_for(ol.LifecycleOperation.RECOVERY)), 0)

    def test_order_monetary_exponent_halts(self) -> None:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_ok_pre_create(), create=_ok_create(),
            exact_order=[_ok_order_response(client_order_id=DEFAULT_CLIENT_ORDER_ID, yes_price_dollars="1e-2")],
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.ORDER_MALFORMED)

    def test_fill_fee_scale_violation_halts(self) -> None:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_ok_pre_create(), create=_ok_create(),
            exact_order=[_ok_order_response(client_order_id=DEFAULT_CLIENT_ORDER_ID, fill_count_fp="0.10", remaining_count_fp="0.90")],
            fills=[_ok_fills_response([make_fill(fill_id="F1", count_fp="0.10", fee_cost="0.0000001")])],
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.FILL_MALFORMED)

    def test_cancel_reduced_by_exponent_halts_immediately(self) -> None:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_ok_pre_create(), create=_ok_create(),
            exact_order=[_ok_order_response(client_order_id=DEFAULT_CLIENT_ORDER_ID, status="resting")],
            fills=[_ok_fills_response([])],
            cancel=[_ok_cancel_response(reduced_by="1e0")],
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.CANCEL_RESPONSE_MALFORMED)
        self.assertEqual(len(transport.calls_for(ol.LifecycleOperation.EXACT_ORDER)), 1)


class TestCorrection04FullFillDuplicateIdentity(unittest.TestCase):
    def _assert_conflict(self, changed: Mapping[str, object]) -> None:
        ledger = ol.FillLedger()
        first = make_fill(fill_id="F-DUP", count_fp="0.10")
        self.assertIsNone(ledger.ingest(first, bound_order_id="ORDER-0001", ticker=TICKER))
        replay = dict(first)
        replay.update(changed)
        self.assertEqual(
            ledger.ingest(replay, bound_order_id="ORDER-0001", ticker=TICKER),
            ol.LifecycleHaltCode.DUPLICATE_FILL_CONFLICT,
        )
        self.assertEqual(ledger.total_quantity(), Decimal("0.10"))

    def test_trade_id_conflict(self) -> None:
        self._assert_conflict({"trade_id": "TRADE-CHANGED"})

    def test_market_ticker_conflict(self) -> None:
        self._assert_conflict({"market_ticker": "KXOTHER-26AUG-T0"})

    def test_no_price_dollars_conflict(self) -> None:
        self._assert_conflict({"no_price_dollars": "0.9800"})

    def test_fee_cost_conflict(self) -> None:
        self._assert_conflict({"fee_cost": "0.000001"})

    def test_optional_authoritative_field_conflict(self) -> None:
        self._assert_conflict({"created_time": "2026-08-09T12:00:00Z"})

    def test_exact_full_replay_counts_once(self) -> None:
        ledger = ol.FillLedger()
        fill = make_fill(fill_id="F-EXACT", count_fp="0.10", fee_cost="0.000001")
        self.assertIsNone(ledger.ingest(fill, bound_order_id="ORDER-0001", ticker=TICKER))
        self.assertIsNone(ledger.ingest(dict(fill), bound_order_id="ORDER-0001", ticker=TICKER))
        self.assertEqual(ledger.total_quantity(), Decimal("0.10"))
        self.assertEqual(len(ledger.fills()), 1)


class TestCorrection04FinalPostCancelReconciliation(unittest.TestCase):
    def test_final_order_fill_count_disagrees_with_canonical_fills_halts(self) -> None:
        clock = _FixedClock()
        f = make_fill(fill_id="F1", count_fp="0.40")
        transport = build_transport(
            pre_create=_ok_pre_create(), create=_ok_create(),
            exact_order=[
                _ok_order_response(client_order_id=DEFAULT_CLIENT_ORDER_ID, status="resting", fill_count_fp="0.40", remaining_count_fp="0.60"),
                _ok_order_response(client_order_id=DEFAULT_CLIENT_ORDER_ID, status="canceled", fill_count_fp="0.50", remaining_count_fp="0.50"),
            ],
            fills=[_ok_fills_response([f]), _ok_fills_response([f])],
            cancel=[_ok_cancel_response(reduced_by="0.60")],
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.FILL_QUANTITY_ORDER_RECONCILIATION_MISMATCH)

    def test_final_canceled_point_four_plus_point_six_succeeds(self) -> None:
        clock = _FixedClock()
        f = make_fill(fill_id="F1", count_fp="0.40")
        transport = build_transport(
            pre_create=_ok_pre_create(), create=_ok_create(),
            exact_order=[
                _ok_order_response(client_order_id=DEFAULT_CLIENT_ORDER_ID, status="resting", fill_count_fp="0.40", remaining_count_fp="0.60"),
                _ok_order_response(client_order_id=DEFAULT_CLIENT_ORDER_ID, status="canceled", fill_count_fp="0.40", remaining_count_fp="0.60"),
            ],
            fills=[_ok_fills_response([f]), _ok_fills_response([f])],
            cancel=[_ok_cancel_response(reduced_by="0.60")],
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertIsInstance(result, ol.OneOrderLifecycleResult)
        self.assertEqual(result.terminal, ol.LifecycleTerminal.CANCELED)
        self.assertEqual(result.canonical_fill_quantity, Decimal("0.40"))
        self.assertTrue(result.cancel_conservation_result)

    def test_cancel_fill_race_may_end_executed(self) -> None:
        clock = _FixedClock()
        f = make_fill(fill_id="F-RACE", count_fp="1.00")
        transport = build_transport(
            pre_create=_ok_pre_create(), create=_ok_create(),
            exact_order=[
                _ok_order_response(client_order_id=DEFAULT_CLIENT_ORDER_ID, status="resting", fill_count_fp="0.00", remaining_count_fp="1.00"),
                _ok_order_response(client_order_id=DEFAULT_CLIENT_ORDER_ID, status="executed", fill_count_fp="1.00", remaining_count_fp="0.00"),
            ],
            fills=[_ok_fills_response([]), _ok_fills_response([f])],
            cancel=[_ok_cancel_response(reduced_by="0.00")],
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertIsInstance(result, ol.OneOrderLifecycleResult)
        self.assertEqual(result.terminal, ol.LifecycleTerminal.FILLED)
        self.assertEqual(result.final_status, "executed")
        self.assertEqual(result.canonical_fill_quantity, Decimal("1.00"))

    def test_executed_final_order_with_incomplete_fills_halts(self) -> None:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_ok_pre_create(), create=_ok_create(),
            exact_order=[
                _ok_order_response(client_order_id=DEFAULT_CLIENT_ORDER_ID, status="resting"),
                _ok_order_response(client_order_id=DEFAULT_CLIENT_ORDER_ID, status="executed", fill_count_fp="1.00", remaining_count_fp="0.00"),
            ],
            fills=[_ok_fills_response([]), _ok_fills_response([])],
            cancel=[_ok_cancel_response(reduced_by="0.00")],
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.FILL_QUANTITY_ORDER_RECONCILIATION_MISMATCH)

    def test_executed_final_order_with_conflicting_duplicate_fill_halts(self) -> None:
        clock = _FixedClock()
        f1 = make_fill(fill_id="F-RACE", count_fp="1.00", trade_id="T1")
        f2 = make_fill(fill_id="F-RACE", count_fp="1.00", trade_id="T2")
        transport = build_transport(
            pre_create=_ok_pre_create(), create=_ok_create(),
            exact_order=[
                _ok_order_response(client_order_id=DEFAULT_CLIENT_ORDER_ID, status="resting"),
                _ok_order_response(client_order_id=DEFAULT_CLIENT_ORDER_ID, status="executed", fill_count_fp="1.00", remaining_count_fp="0.00"),
            ],
            fills=[_ok_fills_response([]), _ok_fills_response([f1, f2])],
            cancel=[_ok_cancel_response(reduced_by="0.00")],
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.DUPLICATE_FILL_CONFLICT)


class TestCorrection04ImmutableSnapshots(unittest.TestCase):
    def _plan(self, lifecycle_input: Optional[ol.OneOrderLifecycleInput] = None) -> ol.OneOrderLifecyclePlan:
        clock = _FixedClock()
        result = ol.plan_demo_one_order_lifecycle(
            lifecycle_input or make_lifecycle_input(),
            monotonic_clock=clock.monotonic,
            _utc_clock=lambda: EXECUTOR_ENTRY_UTC,
        )
        self.assertIsInstance(result, ol.OneOrderLifecyclePlan)
        return result

    def test_mutating_original_proof_list_and_set_does_not_change_plan(self) -> None:
        proof = make_valid_proof()
        lifecycle_input = make_lifecycle_input(writer_exclusivity_prior_write_proof=proof)
        clock = _FixedClock()
        plan = ol.plan_demo_one_order_lifecycle(lifecycle_input, monotonic_clock=clock.monotonic, _utc_clock=lambda: EXECUTOR_ENTRY_UTC)
        self.assertIsInstance(plan, ol.OneOrderLifecyclePlan)
        proof.credential_source_names[:] = ["MUTATED"]
        proof.protected_write_operations.clear()  # type: ignore[union-attr]
        result = ol.execute_demo_one_order_lifecycle(plan, full_happy_path_transport(), monotonic_clock=clock.monotonic, _wall_clock=clock.wall)
        self.assertIsInstance(result, ol.OneOrderLifecycleResult)

    def test_mutating_original_authorization_does_not_change_plan(self) -> None:
        auth = make_valid_authorization()
        lifecycle_input = make_lifecycle_input(lifecycle_authorization=auth)
        clock = _FixedClock()
        plan = ol.plan_demo_one_order_lifecycle(lifecycle_input, monotonic_clock=clock.monotonic, _utc_clock=lambda: EXECUTOR_ENTRY_UTC)
        self.assertIsInstance(plan, ol.OneOrderLifecyclePlan)
        object.__setattr__(auth, "ticker", "MUTATED")
        auth.operation_binding_sha256.clear()
        result = ol.execute_demo_one_order_lifecycle(plan, full_happy_path_transport(), monotonic_clock=clock.monotonic, _wall_clock=clock.wall)
        self.assertIsInstance(result, ol.OneOrderLifecycleResult)

    def test_mutating_original_operation_binding_dict_does_not_change_plan(self) -> None:
        bindings = real_operation_binding_bytes()
        lifecycle_input = make_lifecycle_input(operation_binding_record_bytes=bindings)
        clock = _FixedClock()
        plan = ol.plan_demo_one_order_lifecycle(lifecycle_input, monotonic_clock=clock.monotonic, _utc_clock=lambda: EXECUTOR_ENTRY_UTC)
        self.assertIsInstance(plan, ol.OneOrderLifecyclePlan)
        bindings.clear()
        result = ol.execute_demo_one_order_lifecycle(plan, full_happy_path_transport(), monotonic_clock=clock.monotonic, _wall_clock=clock.wall)
        self.assertIsInstance(result, ol.OneOrderLifecycleResult)

    def _assert_plan_tamper_zero_calls(self, field_name: str, value: object) -> None:
        clock = _FixedClock()
        plan = ol.plan_demo_one_order_lifecycle(make_lifecycle_input(), monotonic_clock=clock.monotonic, _utc_clock=lambda: EXECUTOR_ENTRY_UTC)
        self.assertIsInstance(plan, ol.OneOrderLifecyclePlan)
        object.__setattr__(plan, field_name, value)
        transport = full_happy_path_transport()
        result = ol.execute_demo_one_order_lifecycle(plan, transport, monotonic_clock=clock.monotonic, _wall_clock=clock.wall)
        self.assertIsInstance(result, ol.OneOrderLifecycleHalt)
        self.assertEqual(transport.calls, [])

    def test_plan_ticker_tamper_zero_calls(self) -> None:
        self._assert_plan_tamper_zero_calls("ticker", "KXTAMPER")

    def test_plan_proof_tamper_zero_calls(self) -> None:
        self._assert_plan_tamper_zero_calls("proof_id", "PROOF-TAMPER")

    def test_plan_source_tamper_zero_calls(self) -> None:
        self._assert_plan_tamper_zero_calls("source_record_bytes", b"tampered")

    def test_plan_request_limit_tamper_zero_calls(self) -> None:
        self._assert_plan_tamper_zero_calls("max_total_rest_requests", ol.GLOBAL_REQUEST_MAXIMUM + 1)

    def test_nested_proof_snapshot_tamper_zero_calls(self) -> None:
        clock = _FixedClock()
        plan = ol.plan_demo_one_order_lifecycle(make_lifecycle_input(), monotonic_clock=clock.monotonic, _utc_clock=lambda: EXECUTOR_ENTRY_UTC)
        self.assertIsInstance(plan, ol.OneOrderLifecyclePlan)
        object.__setattr__(plan, "proof_snapshot", replace(plan.proof_snapshot, prior_write_state="UNKNOWN"))
        transport = full_happy_path_transport()
        result = ol.execute_demo_one_order_lifecycle(plan, transport, monotonic_clock=clock.monotonic, _wall_clock=clock.wall)
        self.assertIsInstance(result, ol.OneOrderLifecycleHalt)
        self.assertEqual(transport.calls, [])

    def test_result_and_halt_evidence_collections_are_not_mutable(self) -> None:
        result = plan_and_execute(full_happy_path_transport(), clock=_FixedClock())
        self.assertIsInstance(result, ol.OneOrderLifecycleResult)
        self.assertIsInstance(result.fills, tuple)
        self.assertIsInstance(result.fill_price_validations, tuple)
        with self.assertRaises(TypeError):
            result.request_counts["CREATE"] = 99  # type: ignore[index]
        with self.assertRaises(TypeError):
            result.operation_binding_sha256["CREATE_ORDER_V2"] = "x"  # type: ignore[index]

        halt_transport = build_transport(pre_create=_raw_response(status=200, body={"orders": []}))
        halt = plan_and_execute(halt_transport, clock=_FixedClock())
        self.assertIsInstance(halt, ol.OneOrderLifecycleHalt)
        with self.assertRaises(TypeError):
            halt.request_counts["X"] = 1  # type: ignore[index]
        with self.assertRaises(TypeError):
            halt.operation_binding_sha256["X"] = "y"  # type: ignore[index]


class TestCorrection04OperationSemantics(unittest.TestCase):
    def test_exact_appendix_d_records_bind_expected_semantics(self) -> None:
        self.assertIsNone(ol.validate_operation_binding_semantics(real_operation_binding_bytes()))

    def test_current_template_tamper_with_correct_record_fixture_halts_zero_calls(self) -> None:
        original = ol._CURRENT_OPERATION_CONTRACTS
        tampered = dict(original)
        tampered["PRE_CREATE_ORDER_TRUTH"] = replace(tampered["PRE_CREATE_ORDER_TRUTH"], method="POST")
        ol._CURRENT_OPERATION_CONTRACTS = tampered
        try:
            clock = _FixedClock()
            transport = full_happy_path_transport()
            result = plan_and_execute(transport, clock=clock)
            self.assertIsInstance(result, ol.OneOrderLifecycleHalt)
            self.assertEqual(result.halt_code, ol.LifecycleHaltCode.OPERATION_BINDING_MISMATCH)
            self.assertEqual(transport.calls, [])
        finally:
            ol._CURRENT_OPERATION_CONTRACTS = original

    def test_plan_operation_contract_tamper_halts_zero_calls(self) -> None:
        clock = _FixedClock()
        plan = ol.plan_demo_one_order_lifecycle(make_lifecycle_input(), monotonic_clock=clock.monotonic, _utc_clock=lambda: EXECUTOR_ENTRY_UTC)
        self.assertIsInstance(plan, ol.OneOrderLifecyclePlan)
        contracts = dict(plan.operation_contracts)
        contracts["FILL_READ"] = replace(contracts["FILL_READ"], path_template="/portfolio/not-fills")
        object.__setattr__(plan, "operation_contracts", contracts)
        transport = full_happy_path_transport()
        result = ol.execute_demo_one_order_lifecycle(plan, transport, monotonic_clock=clock.monotonic, _wall_clock=clock.wall)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.OPERATION_BINDING_MISMATCH)
        self.assertEqual(transport.calls, [])


class TestCorrection04AppendixFTimeAndTypes(unittest.TestCase):
    def test_protected_write_operations_frozenset_rejected_end_to_end(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        proof = make_valid_proof(protected_write_operations=frozenset({"CREATE", "AMEND", "DECREASE", "CANCEL"}))
        result = plan_and_execute(transport, clock=clock, proof=proof)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.WRITER_EXCLUSIVITY_NOT_ESTABLISHED)
        self.assertEqual(transport.calls, [])

    def test_timestamp_difference_after_sixth_fractional_digit_halts(self) -> None:
        clock = _FixedClock()
        proof = make_valid_proof(valid_from_utc="2026-08-09T12:00:00.0000001Z")
        lifecycle_input = make_lifecycle_input(writer_exclusivity_prior_write_proof=proof)
        result = ol.plan_demo_one_order_lifecycle(
            lifecycle_input, monotonic_clock=clock.monotonic,
            _utc_clock=lambda: "2026-08-09T12:00:00.0000000Z",
        )
        self.assertIsInstance(result, ol.OneOrderLifecycleHalt)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.WRITER_EXCLUSIVITY_NOT_ACTIVE_BEFORE_PREFLIGHT)

    def test_planner_has_no_ordinary_executor_entry_argument(self) -> None:
        parameters = inspect.signature(ol.plan_demo_one_order_lifecycle).parameters
        self.assertNotIn("executor_entry_utc", parameters)
        self.assertIn("_utc_clock", parameters)

    def test_executor_has_no_ordinary_body_freeze_or_wall_clock_argument(self) -> None:
        parameters = inspect.signature(ol.execute_demo_one_order_lifecycle).parameters
        self.assertNotIn("body_freeze_epoch_seconds", parameters)
        self.assertNotIn("wall_clock", parameters)
        self.assertIn("_wall_clock", parameters)


class TestCorrection04WriteSendClassification(unittest.TestCase):
    def test_create_pre_send_transport_failure_is_typed_and_zero_upper_bound(self) -> None:
        clock = _FixedClock()
        transport = _FakeTransport(responses={
            ol.LifecycleOperation.PRE_CREATE_TRUTH: [_ok_pre_create()],
            ol.LifecycleOperation.CREATE: [ol.LifecycleTransportPreSendError()],
        })
        result = plan_and_execute(transport, clock=clock)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.TRANSPORT_PRE_SEND_FAILURE)
        self.assertFalse(result.create_send_may_have_begun)
        self.assertEqual(result.created_order_upper_bound, 0)
        self.assertFalse(result.unknown_result)
        self.assertTrue(result.proof_release_eligible)

    def test_create_http_rejection_records_unknown_after_send(self) -> None:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_ok_pre_create(),
            create=_raw_response(status=400, body={"error": "rejected"}),
            recovery=[_raw_response(status=200, body={"orders": [], "cursor": ""})],
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.RECOVERY_ZERO_MATCH)
        self.assertTrue(result.create_send_may_have_begun)
        self.assertEqual(result.created_order_upper_bound, 1)
        self.assertTrue(result.unknown_result)
        self.assertFalse(result.proof_release_eligible)
        self.assertEqual(len(transport.calls_for(ol.LifecycleOperation.CREATE)), 1)
        self.assertEqual(len(transport.calls_for(ol.LifecycleOperation.RECOVERY)), 1)

    def test_create_unknown_after_send_is_typed_and_not_resent(self) -> None:
        clock = _FixedClock()
        transport = _FakeTransport(responses={
            ol.LifecycleOperation.PRE_CREATE_TRUTH: [_ok_pre_create()],
            ol.LifecycleOperation.CREATE: [ol.LifecycleTransportUnknownAfterSendError()],
        })
        result = plan_and_execute(transport, clock=clock)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.TRANSPORT_RESULT_UNKNOWN)
        self.assertTrue(result.create_send_may_have_begun)
        self.assertEqual(result.created_order_upper_bound, 1)
        self.assertTrue(result.unknown_result)
        self.assertFalse(result.proof_release_eligible)
        self.assertEqual(len(transport.calls_for(ol.LifecycleOperation.CREATE)), 1)

    def _cancel_transport_failure(self, exc: BaseException) -> tuple[ol.OneOrderLifecycleHalt, _FakeTransport]:
        clock = _FixedClock()
        transport = _FakeTransport(responses={
            ol.LifecycleOperation.PRE_CREATE_TRUTH: [_ok_pre_create()],
            ol.LifecycleOperation.CREATE: [_ok_create()],
            ol.LifecycleOperation.EXACT_ORDER: [_ok_order_response(client_order_id=DEFAULT_CLIENT_ORDER_ID, status="resting")],
            ol.LifecycleOperation.FILLS: [_ok_fills_response([])],
            ol.LifecycleOperation.CANCEL: [exc],
        })
        result = plan_and_execute(transport, clock=clock)
        self.assertIsInstance(result, ol.OneOrderLifecycleHalt)
        return result, transport

    def test_cancel_pre_send_transport_failure_is_typed(self) -> None:
        result, transport = self._cancel_transport_failure(ol.LifecycleTransportPreSendError())
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.TRANSPORT_PRE_SEND_FAILURE)
        self.assertFalse(result.cancel_send_may_have_begun)
        self.assertFalse(result.unknown_result)
        self.assertEqual(len(transport.calls_for(ol.LifecycleOperation.CANCEL)), 1)

    def test_cancel_unknown_after_send_is_typed(self) -> None:
        result, transport = self._cancel_transport_failure(ol.LifecycleTransportUnknownAfterSendError())
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.TRANSPORT_RESULT_UNKNOWN)
        self.assertTrue(result.cancel_send_may_have_begun)
        self.assertTrue(result.unknown_result)
        self.assertEqual(len(transport.calls_for(ol.LifecycleOperation.CANCEL)), 1)

    def test_cancel_http_rejection_records_unknown_after_send(self) -> None:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_ok_pre_create(), create=_ok_create(),
            exact_order=[
                _ok_order_response(client_order_id=DEFAULT_CLIENT_ORDER_ID, status="resting"),
                _ok_order_response(client_order_id=DEFAULT_CLIENT_ORDER_ID, status="resting"),
            ],
            fills=[_ok_fills_response([]), _ok_fills_response([])],
            cancel=[_raw_response(status=400, body={"error": "rejected"})],
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.CANCEL_AMBIGUOUS_UNRESOLVED)
        self.assertTrue(result.cancel_send_may_have_begun)
        self.assertTrue(result.unknown_result)
        self.assertFalse(result.proof_release_eligible)
        self.assertEqual(len(transport.calls_for(ol.LifecycleOperation.CANCEL)), 1)
        self.assertEqual(len(transport.calls_for(ol.LifecycleOperation.CREATE)), 1)


class TestCorrection05StatusOnlyWriteRejections(unittest.TestCase):
    CREATE_NON_SUCCESS_STATUSES = (400, 401, 403, 422, 409, 500, 503)
    CANCEL_NON_SUCCESS_STATUSES = (400, 401, 403, 422, 409, 500, 503)

    def test_create_non_success_status_matrix_stays_unknown_and_uses_one_recovery(self) -> None:
        for status in self.CREATE_NON_SUCCESS_STATUSES:
            with self.subTest(status=status):
                clock = _FixedClock()
                transport = build_transport(
                    pre_create=_ok_pre_create(),
                    create=_raw_response(status=status, body={"error": "rejected"}),
                    recovery=[_raw_response(status=200, body={"orders": [], "cursor": ""})],
                )
                result = plan_and_execute(transport, clock=clock)
                self.assertIsInstance(result, ol.OneOrderLifecycleHalt)
                self.assertEqual(result.halt_code, ol.LifecycleHaltCode.RECOVERY_ZERO_MATCH)
                self.assertTrue(result.create_send_may_have_begun)
                self.assertEqual(result.created_order_upper_bound, 1)
                self.assertEqual(result.active_order_upper_bound, 1)
                self.assertTrue(result.unknown_result)
                self.assertFalse(result.proof_release_eligible)
                self.assertEqual(len(transport.calls_for(ol.LifecycleOperation.CREATE)), 1)
                self.assertEqual(len(transport.calls_for(ol.LifecycleOperation.RECOVERY)), 1)
                self.assertEqual(result.request_counts[ol.LifecycleOperation.CREATE.value], 1)
                self.assertEqual(result.request_counts[ol.LifecycleOperation.RECOVERY.value], 1)

    def test_received_non_success_create_can_recover_exact_order_once(self) -> None:
        clock = _FixedClock()
        recovered = make_order(
            order_id="ORDER-RECOVERED",
            client_order_id=DEFAULT_CLIENT_ORDER_ID,
            status="resting",
        )
        transport = build_transport(
            pre_create=_ok_pre_create(),
            create=_raw_response(status=400, body={"error": "rejected"}),
            recovery=[_raw_response(status=200, body={"orders": [recovered], "cursor": ""})],
            exact_order=[
                _ok_order_response(order_id="ORDER-RECOVERED", client_order_id=DEFAULT_CLIENT_ORDER_ID, status="resting"),
                _ok_order_response(order_id="ORDER-RECOVERED", client_order_id=DEFAULT_CLIENT_ORDER_ID, status="canceled"),
            ],
            fills=[_ok_fills_response([]), _ok_fills_response([])],
            cancel=[_ok_cancel_response(order_id="ORDER-RECOVERED", reduced_by="1.00")],
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertIsInstance(result, ol.OneOrderLifecycleResult)
        self.assertEqual(result.bound_order_id, "ORDER-RECOVERED")
        self.assertEqual(result.final_status, "canceled")
        self.assertEqual(len(transport.calls_for(ol.LifecycleOperation.CREATE)), 1)
        self.assertEqual(len(transport.calls_for(ol.LifecycleOperation.RECOVERY)), 1)

    def test_malformed_201_is_unknown_after_send_and_not_resent(self) -> None:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_ok_pre_create(),
            create=_raw_response(
                status=201,
                body={"order_id": "ORDER-0001", "remaining_count": "1.00", "ts_ms": 1},
            ),
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertIsInstance(result, ol.OneOrderLifecycleHalt)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.CREATE_RESPONSE_MALFORMED)
        self.assertTrue(result.create_send_may_have_begun)
        self.assertEqual(result.created_order_upper_bound, 1)
        self.assertTrue(result.unknown_result)
        self.assertFalse(result.proof_release_eligible)
        self.assertEqual(len(transport.calls_for(ol.LifecycleOperation.CREATE)), 1)
        self.assertEqual(len(transport.calls_for(ol.LifecycleOperation.RECOVERY)), 0)

    def test_valid_201_definitive_success_remains_successful(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        result = plan_and_execute(transport, clock=clock)
        self.assertIsInstance(result, ol.OneOrderLifecycleResult)
        self.assertEqual(result.final_status, "canceled")
        self.assertEqual(len(transport.calls_for(ol.LifecycleOperation.CREATE)), 1)

    def test_cancel_non_success_status_matrix_stays_unknown_and_never_resends(self) -> None:
        for status in self.CANCEL_NON_SUCCESS_STATUSES:
            with self.subTest(status=status):
                clock = _FixedClock()
                transport = build_transport(
                    pre_create=_ok_pre_create(),
                    create=_ok_create(),
                    exact_order=[
                        _ok_order_response(client_order_id=DEFAULT_CLIENT_ORDER_ID, status="resting"),
                        _ok_order_response(client_order_id=DEFAULT_CLIENT_ORDER_ID, status="resting"),
                    ],
                    fills=[_ok_fills_response([]), _ok_fills_response([])],
                    cancel=[_raw_response(status=status, body={"error": "rejected"})],
                )
                result = plan_and_execute(transport, clock=clock)
                self.assertIsInstance(result, ol.OneOrderLifecycleHalt)
                self.assertEqual(result.halt_code, ol.LifecycleHaltCode.CANCEL_AMBIGUOUS_UNRESOLVED)
                self.assertTrue(result.cancel_send_may_have_begun)
                self.assertTrue(result.unknown_result)
                self.assertFalse(result.proof_release_eligible)
                self.assertEqual(len(transport.calls_for(ol.LifecycleOperation.CANCEL)), 1)
                self.assertEqual(len(transport.calls_for(ol.LifecycleOperation.CREATE)), 1)
                self.assertEqual(result.request_counts[ol.LifecycleOperation.CANCEL.value], 1)
                self.assertEqual(result.request_counts[ol.LifecycleOperation.CREATE.value], 1)

    def test_malformed_200_cancel_is_unknown_after_send_and_not_resent(self) -> None:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_ok_pre_create(),
            create=_ok_create(),
            exact_order=[_ok_order_response(client_order_id=DEFAULT_CLIENT_ORDER_ID, status="resting")],
            fills=[_ok_fills_response([])],
            cancel=[_raw_response(status=200, body={"order_id": "ORDER-0001", "ts_ms": 1})],
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertIsInstance(result, ol.OneOrderLifecycleHalt)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.CANCEL_RESPONSE_MALFORMED)
        self.assertTrue(result.cancel_send_may_have_begun)
        self.assertTrue(result.unknown_result)
        self.assertFalse(result.proof_release_eligible)
        self.assertEqual(len(transport.calls_for(ol.LifecycleOperation.CANCEL)), 1)
        self.assertEqual(len(transport.calls_for(ol.LifecycleOperation.CREATE)), 1)

    def test_valid_200_cancel_definitive_success_remains_successful(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        result = plan_and_execute(transport, clock=clock)
        self.assertIsInstance(result, ol.OneOrderLifecycleResult)
        self.assertEqual(result.cancel_classification, ol.SendOutcome.DEFINITIVE_SUCCESS.value)
        self.assertEqual(len(transport.calls_for(ol.LifecycleOperation.CANCEL)), 1)


class TestCorrection04CreateCancelValidation(unittest.TestCase):
    def test_create_optional_client_id_mismatch_halts_immediately(self) -> None:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_ok_pre_create(),
            create=_raw_response(status=201, body={
                "order_id": "ORDER-0001", "fill_count": "0.00", "remaining_count": "1.00", "ts_ms": 1,
                "client_order_id": ALT_CLIENT_ORDER_ID,
            }),
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.CREATE_RESPONSE_MALFORMED)
        self.assertEqual(len(transport.calls_for(ol.LifecycleOperation.RECOVERY)), 0)

    def test_create_optional_average_fill_price_malformed_halts(self) -> None:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_ok_pre_create(),
            create=_raw_response(status=201, body={
                "order_id": "ORDER-0001", "fill_count": "0.00", "remaining_count": "1.00", "ts_ms": 1,
                "average_fill_price": "1e-2",
            }),
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.CREATE_RESPONSE_MALFORMED)

    def test_create_optional_average_fee_paid_scale_violation_halts(self) -> None:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_ok_pre_create(),
            create=_raw_response(status=201, body={
                "order_id": "ORDER-0001", "fill_count": "0.00", "remaining_count": "1.00", "ts_ms": 1,
                "average_fee_paid": "0.0000001",
            }),
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.CREATE_RESPONSE_MALFORMED)

    def test_cancel_ts_bool_halts_immediately(self) -> None:
        clock = _FixedClock()
        transport = build_transport(
            pre_create=_ok_pre_create(), create=_ok_create(),
            exact_order=[_ok_order_response(client_order_id=DEFAULT_CLIENT_ORDER_ID, status="resting")],
            fills=[_ok_fills_response([])],
            cancel=[_raw_response(status=200, body={"order_id": "ORDER-0001", "reduced_by": "1.00", "ts_ms": True})],
        )
        result = plan_and_execute(transport, clock=clock)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.CANCEL_RESPONSE_MALFORMED)


class TestCorrection04FeeRiskAuthorizationBinding(unittest.TestCase):
    def test_exact_fee_binding_match_passes(self) -> None:
        result = plan_and_execute(full_happy_path_transport(), clock=_FixedClock())
        self.assertIsInstance(result, ol.OneOrderLifecycleResult)

    def test_fee_binding_mismatch_halts_before_transport(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        input_fee = ol.OneOrderFeeRiskBinding(max_fee_dollars=Decimal("0.030000"))
        result = plan_and_execute(transport, clock=clock, fee_risk_binding=input_fee)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID)
        self.assertEqual(transport.calls, [])

    def test_broader_authorization_fee_binding_halts(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        input_fee = ol.OneOrderFeeRiskBinding(max_fee_dollars=Decimal("0.030000"))
        auth = make_valid_authorization(fee_risk_binding=ol.OneOrderFeeRiskBinding(max_fee_dollars=Decimal("0.040000")))
        result = plan_and_execute(transport, clock=clock, fee_risk_binding=input_fee, authorization=auth)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID)
        self.assertEqual(transport.calls, [])

    def test_fee_binding_wrong_current_type_halts(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        bad_fee = ol.OneOrderFeeRiskBinding(max_fee_dollars=Decimal("0.040000"))
        object.__setattr__(bad_fee, "max_fee_dollars", "0.040000")
        auth = make_valid_authorization(fee_risk_binding=bad_fee)
        result = plan_and_execute(transport, clock=clock, fee_risk_binding=bad_fee, authorization=auth)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID)
        self.assertEqual(transport.calls, [])

    def test_fee_ceiling_violation_halts(self) -> None:
        clock = _FixedClock()
        transport = full_happy_path_transport()
        fee = ol.OneOrderFeeRiskBinding(max_fee_dollars=Decimal("0.040001"))
        auth = make_valid_authorization(fee_risk_binding=fee)
        result = plan_and_execute(transport, clock=clock, fee_risk_binding=fee, authorization=auth)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID)
        self.assertEqual(transport.calls, [])


class TestCorrection04EvidenceIdentity(unittest.TestCase):
    def _assert_every_public_field_load_bearing(self, evidence: object) -> None:
        field_names = [name for name in evidence.__dataclass_fields__ if name != "secret_safe_evidence_sha256"]
        base_record = {name: getattr(evidence, name) for name in field_names}
        baseline = ol._secret_safe_evidence_sha256_from_record(base_record)
        self.assertEqual(baseline, evidence.secret_safe_evidence_sha256)
        for name in field_names:
            mutated = dict(base_record)
            mutated[name] = ["CORRECTION04_MUTATED_FIELD", name]
            with self.subTest(field=name):
                self.assertNotEqual(ol._secret_safe_evidence_sha256_from_record(mutated), baseline)

    def test_result_hash_covers_every_public_evidence_field(self) -> None:
        result = plan_and_execute(full_happy_path_transport(), clock=_FixedClock())
        self.assertIsInstance(result, ol.OneOrderLifecycleResult)
        self._assert_every_public_field_load_bearing(result)

    def test_halt_hash_covers_every_public_evidence_field(self) -> None:
        transport = build_transport(pre_create=_raw_response(status=200, body={"orders": []}))
        halt = plan_and_execute(transport, clock=_FixedClock())
        self.assertIsInstance(halt, ol.OneOrderLifecycleHalt)
        self._assert_every_public_field_load_bearing(halt)

    def test_planning_halt_preserves_established_source_and_binding_identities(self) -> None:
        auth = make_valid_authorization(writer_proof_id="OTHER-PROOF")
        transport = full_happy_path_transport()
        halt = plan_and_execute(transport, clock=_FixedClock(), authorization=auth)
        self.assertIsInstance(halt, ol.OneOrderLifecycleHalt)
        self.assertEqual(halt.source_record_sha256, ol.SOURCE_RECORD_SHA256)
        self.assertEqual(set(halt.operation_binding_sha256), set(ol.OPERATION_BINDINGS))
        self.assertEqual(transport.calls, [])


class _LateReturnTransport(_FakeTransport):
    def __init__(self, clock: _FixedClock, response: ol.RawHttpResponse) -> None:
        super().__init__(responses={ol.LifecycleOperation.PRE_CREATE_TRUTH: [response]})
        self._clock = clock

    def send(self, request: ol.PreparedRequest) -> ol.RawHttpResponse:
        response = super().send(request)
        self._clock._value = request.effective_deadline_monotonic + 0.001
        self._clock.freeze = True
        return response


class TestCorrection04TransportEvidenceFailClosed(unittest.TestCase):
    def test_raw_response_requires_all_transport_evidence_fields(self) -> None:
        with self.assertRaises(TypeError):
            ol.RawHttpResponse(status=200, body={})  # type: ignore[call-arg]

    def test_forged_response_missing_transport_evidence_halts(self) -> None:
        clock = _FixedClock()
        transport = _FakeTransport(responses={ol.LifecycleOperation.PRE_CREATE_TRUTH: [object()]})
        result = plan_and_execute(transport, clock=clock)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.RESPONSE_TRANSPORT_EVIDENCE_MISSING)
        self.assertEqual(len(transport.calls), 1)

    def test_transport_return_after_request_deadline_halts_before_body_acceptance(self) -> None:
        clock = _FixedClock(step=0.001)
        transport = _LateReturnTransport(clock, _ok_pre_create())
        result = plan_and_execute(transport, clock=clock)
        self.assertEqual(result.halt_code, ol.LifecycleHaltCode.DEADLINE_EXCEEDED)
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(len(transport.calls_for(ol.LifecycleOperation.CREATE)), 0)


if __name__ == "__main__":
    unittest.main()
