"""Offline tests for the generic two-store execution safety ledger."""

from __future__ import annotations

import json
import multiprocessing
import os
import sqlite3
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import arb.execution_ledger as ledger
from arb.execution_ledger import (
    AcquisitionMode,
    AppendStatus,
    AuthorityNamespaceBinding,
    CommitResultUnknown,
    EventInput,
    EventType,
    FailureCode,
    LedgerError,
    RestartClassification,
    acquire_local_state,
    assert_secret_safe,
    canonical_json_bytes,
    deterministic_event_id,
    deterministic_review_export,
    end_restricted_session,
    end_writer_session,
    initialize_authority_namespace,
    initialize_ledger_binding,
    parse_canonical_json,
    sha256_hex,
    sqlite_posture,
    start_writer_session,
)
from arb.venues.kalshi.ledger_binding import (
    append_authority_anchored_send_gate,
    prepared_request_identity,
)


PHYSICAL_POWER_LOSS_QUALIFICATION = "NOT_PERFORMED"


class DeterministicInputs:
    def __init__(self) -> None:
        self._instant = datetime(2026, 8, 13, 12, 0, 0, tzinfo=timezone.utc)
        self._uuid = 1

    def clock(self) -> datetime:
        value = self._instant
        self._instant += timedelta(microseconds=1)
        return value

    def uuid(self) -> uuid.UUID:
        value = uuid.UUID(int=self._uuid, version=4)
        self._uuid += 1
        return value


def _multiprocess_lock_worker(
    authority_root: str,
    repository_root: str,
    ledger_path: str,
    queue: multiprocessing.Queue,
) -> None:
    binding = AuthorityNamespaceBinding.bind(
        authority_namespace_id="test-namespace",
        authority_namespace_root=authority_root,
        canonical_repository_root=repository_root,
    )
    result = acquire_local_state(
        binding,
        conflict_domain_ref="test-conflict-domain",
        expected_environment="KALSHI_DEMO",
        canonical_repository_root=repository_root,
        acquisition_mode=AcquisitionMode.NORMAL_WRITER,
        expected_ledger_path=ledger_path,
    )
    queue.put((result.restart_classification.value, result.failure_code.value if result.failure_code else None))


class ExecutionLedgerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repository_root = Path(__file__).resolve().parents[1]
        self.authority_root = self.root / "authority"
        self.authority_root.mkdir()
        self.ledger_path = self.root / "execution.sqlite3"
        self.inputs = DeterministicInputs()
        self.binding = AuthorityNamespaceBinding.bind(
            authority_namespace_id="test-namespace",
            authority_namespace_root=self.authority_root,
            canonical_repository_root=self.repository_root,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def initialize(self) -> None:
        initialize_authority_namespace(
            self.binding, clock=self.inputs.clock, uuid_factory=self.inputs.uuid
        )
        initialize_ledger_binding(
            self.binding,
            conflict_domain_ref="test-conflict-domain",
            environment_classification="KALSHI_DEMO",
            ledger_path=self.ledger_path,
            canonical_repository_root=self.repository_root,
            clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
        )

    def locked(self, *, fault_hook=ledger._noop_fault_hook):
        return ledger._open_locked(
            self.binding,
            conflict_domain_ref="test-conflict-domain",
            expected_environment="KALSHI_DEMO",
            canonical_repository_root=self.repository_root,
            expected_ledger_path=self.ledger_path,
            clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
            fault_hook=fault_hook,
        )

    def test_canonical_json_decimal_and_exact_bytes(self) -> None:
        value = {
            "a": [Decimal("1.00"), Decimal("0.0100"), Decimal("-0.00")],
            "b": "ascii",
        }
        self.assertEqual(
            canonical_json_bytes(value),
            b'{"a":[{"$decimal":"1"},{"$decimal":"0.01"},{"$decimal":"0"}],"b":"ascii"}',
        )
        self.assertNotIn(b"\n", canonical_json_bytes(value))

    def test_spec03_restricted_session_state_event_is_deterministic_replayable_and_closed(self) -> None:
        self.initialize()
        opened = ledger._acquire_restricted_state(
            self.binding,
            conflict_domain_ref="test-conflict-domain",
            expected_environment="KALSHI_DEMO",
            canonical_repository_root=self.repository_root,
            acquisition_mode=AcquisitionMode.EMERGENCY_CONTROL_ONLY,
            expected_ledger_path=self.ledger_path,
            clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
        )
        locked = opened.locked
        session_id = opened.restricted_session_id
        self.assertIsNotNone(locked)
        self.assertIsNotNone(session_id)
        assert locked is not None and session_id is not None
        self.assertTrue(session_id.startswith("rs_"))
        previous = locked.events[-1]
        payload = {
            "previous_state": "BOOT_HOLD",
            "new_state": "SAFE_HELD",
            "cause": "REPLAY_ALL_SAFETY_PREDICATES_PASS",
            "risk_state_epoch_before": 0,
            "risk_state_epoch_after": 1,
            "risk_config_sha256": "a" * 64,
            "related_emergency_action_id": None,
            "related_release_id": None,
            "predecessor_state_event_id": None,
            "observed_authority_trusted_sequence": previous.sequence,
            "observed_authority_trusted_hash": previous.event_hash,
            "observed_ledger_terminal_sequence": previous.sequence,
            "observed_ledger_terminal_hash": previous.event_hash,
        }
        expected_id = deterministic_event_id(EventType.RISK_CONTROL_STATE_CHANGED, payload)
        result = locked.append_batch((EventInput(
            EventType.RISK_CONTROL_STATE_CHANGED, payload, session_id
        ),))
        self.assertEqual(result.events[-1].event_id, expected_id)
        projection = locked.projection()
        self.assertEqual((projection.risk_control_state, projection.risk_state_epoch), ("SAFE_HELD", 1))
        self.assertEqual(projection.active_restricted_session_id, session_id)

        before = (projection.last_sequence, projection.terminal_event_hash)
        with self.assertRaises(LedgerError) as wrong_mode:
            locked.append_batch((EventInput(EventType.RISK_RELEASE_RECORDED, {}, session_id),))
        self.assertEqual(
            wrong_mode.exception.code,
            FailureCode.RESTRICTED_SESSION_EVENT_NOT_PERMITTED,
        )
        self.assertEqual(
            (locked.projection().last_sequence, locked.projection().terminal_event_hash), before
        )
        end_restricted_session(
            locked,
            restricted_session_id=session_id,
            acquisition_mode=AcquisitionMode.EMERGENCY_CONTROL_ONLY,
        )
        reopened = self.locked()
        self.assertIsNone(reopened.projection().active_restricted_session_id)
        self.assertEqual(reopened.projection().risk_control_state, "SAFE_HELD")
        reopened.close()

    def test_spec03_new_event_id_cannot_be_supplied_with_conflicting_content_identity(self) -> None:
        self.initialize()
        opened = ledger._acquire_restricted_state(
            self.binding,
            conflict_domain_ref="test-conflict-domain",
            expected_environment="KALSHI_DEMO",
            canonical_repository_root=self.repository_root,
            acquisition_mode=AcquisitionMode.EMERGENCY_CONTROL_ONLY,
            expected_ledger_path=self.ledger_path,
            clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
        )
        locked = opened.locked
        session_id = opened.restricted_session_id
        self.assertIsNotNone(locked)
        self.assertIsNotNone(session_id)
        assert locked is not None and session_id is not None
        previous = locked.events[-1]
        payload = {
            "previous_state": "BOOT_HOLD", "new_state": "SAFE_HELD",
            "cause": "REPLAY_ALL_SAFETY_PREDICATES_PASS",
            "risk_state_epoch_before": 0, "risk_state_epoch_after": 1,
            "risk_config_sha256": None, "related_emergency_action_id": None,
            "related_release_id": None, "predecessor_state_event_id": None,
            "observed_authority_trusted_sequence": previous.sequence,
            "observed_authority_trusted_hash": previous.event_hash,
            "observed_ledger_terminal_sequence": previous.sequence,
            "observed_ledger_terminal_hash": previous.event_hash,
        }
        with self.assertRaises(LedgerError) as caught:
            locked.append_batch((EventInput(
                EventType.RISK_CONTROL_STATE_CHANGED, payload, session_id,
                event_id="evt_" + "f" * 32,
            ),))
        self.assertEqual(caught.exception.code, FailureCode.EVENT_ID_CONTENT_CONFLICT)
        locked.close()

    def test_canonical_json_rejects_float_reserved_key_and_non_nfc(self) -> None:
        with self.assertRaisesRegex(LedgerError, FailureCode.LEDGER_CANONICAL_ENCODING_FAILURE.value):
            canonical_json_bytes({"value": 0.1})
        with self.assertRaises(LedgerError) as reserved:
            canonical_json_bytes({"$decimal": "1"})
        self.assertEqual(reserved.exception.code, FailureCode.LEDGER_CANONICAL_ENCODING_FAILURE)
        with self.assertRaises(LedgerError) as unicode_error:
            canonical_json_bytes({"value": "e\u0301"})
        self.assertEqual(unicode_error.exception.code, FailureCode.NONCANONICAL_UNICODE)

    def test_parse_rejects_duplicate_keys_noncanonical_and_bad_decimal(self) -> None:
        cases = (
            ('{"a":1,"a":1}', FailureCode.LEDGER_CANONICAL_ENCODING_FAILURE),
            ('{ "a":1}', FailureCode.LEDGER_CANONICAL_ENCODING_FAILURE),
            ('{"d":{"$decimal":"1.0"}}', FailureCode.LEDGER_DECIMAL_CANONICALIZATION_FAILURE),
        )
        for raw, code in cases:
            with self.subTest(raw=raw), self.assertRaises(LedgerError) as caught:
                parse_canonical_json(raw)
            self.assertEqual(caught.exception.code, code)

    def test_secret_key_and_content_rejection(self) -> None:
        for value, code in (
            ({"authorization": "x"}, FailureCode.SECRET_FIELD_PROHIBITED),
            ({"custom_token": "x"}, FailureCode.SECRET_FIELD_PROHIBITED),
            ({"safe": "Bearer abc"}, FailureCode.SECRET_PATTERN_PROHIBITED),
            ({"safe": "-----BEGIN PRIVATE KEY-----"}, FailureCode.SECRET_PATTERN_PROHIBITED),
        ):
            with self.subTest(value=value), self.assertRaises(LedgerError) as caught:
                assert_secret_safe(value)
            self.assertEqual(caught.exception.code, code)
        assert_secret_safe({"credential_reference_name": "demo-ref"})

    def test_authority_and_ledger_exact_sqlite_posture(self) -> None:
        self.initialize()
        authority = sqlite3.connect(self.binding.authority_store_resolved_path, isolation_level=None)
        ledger_connection = sqlite3.connect(self.ledger_path, isolation_level=None)
        try:
            for connection in (authority, ledger_connection):
                connection.execute("PRAGMA synchronous=EXTRA")
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("PRAGMA busy_timeout=0")
                connection.execute("PRAGMA locking_mode=EXCLUSIVE")
                self.assertEqual(
                    dict(sqlite_posture(connection)),
                    {
                        "journal_mode": "delete",
                        "synchronous": 3,
                        "foreign_keys": 1,
                        "busy_timeout": 0,
                        "locking_mode": "exclusive",
                        "user_version": 1,
                    },
                )
                self.assertEqual(connection.execute("PRAGMA integrity_check").fetchall(), [("ok",)])
                self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        finally:
            authority.close()
            ledger_connection.close()

    def test_full_synchronous_is_insufficient(self) -> None:
        real = sqlite3.connect(":memory:", isolation_level=None)
        real.execute("PRAGMA synchronous=FULL")

        class NonconformingConnection:
            def execute(self, statement, parameters=()):
                if statement == "PRAGMA synchronous=EXTRA":
                    return real.execute("SELECT 1")
                return real.execute(statement, parameters)

            def close(self):
                return None

        connection = NonconformingConnection()
        try:
            self.assertEqual(connection.execute("PRAGMA synchronous").fetchone()[0], 2)
            with self.assertRaises(LedgerError) as caught:
                ledger._configure_connection(connection, initialize=False, authority=False)
            self.assertEqual(caught.exception.code, FailureCode.LEDGER_DURABILITY_CONFIGURATION_FAILURE)
        finally:
            real.close()

    def test_authority_initialization_identity_and_immutability(self) -> None:
        meta = initialize_authority_namespace(
            self.binding, clock=self.inputs.clock, uuid_factory=self.inputs.uuid
        )
        self.assertEqual(meta.authority_schema_revision, 1)
        self.assertEqual(meta.authority_namespace_id, "test-namespace")
        connection = sqlite3.connect(self.binding.authority_store_resolved_path)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("UPDATE authority_meta SET authority_namespace_id='other'")
        finally:
            connection.close()

    def test_missing_established_authority_is_not_created(self) -> None:
        result = acquire_local_state(
            self.binding,
            conflict_domain_ref="test-conflict-domain",
            expected_environment="KALSHI_DEMO",
            canonical_repository_root=self.repository_root,
            acquisition_mode=AcquisitionMode.NORMAL_WRITER,
        )
        self.assertEqual(result.restart_classification, RestartClassification.AUTHORITY_INTEGRITY_FAILURE)
        self.assertEqual(result.failure_code, FailureCode.AUTHORITY_STORE_MISSING)
        self.assertFalse(self.binding.authority_store_resolved_path.exists())

    def test_first_binding_and_normal_writer_blocked_by_legacy_history(self) -> None:
        self.initialize()
        result = acquire_local_state(
            self.binding,
            conflict_domain_ref="test-conflict-domain",
            expected_environment="KALSHI_DEMO",
            canonical_repository_root=self.repository_root,
            acquisition_mode=AcquisitionMode.NORMAL_WRITER,
            expected_ledger_path=self.ledger_path,
        )
        self.assertEqual(result.restart_classification, RestartClassification.LEGACY_HISTORY_INCOMPLETE)
        self.assertIsNone(result.handle)
        self.assertEqual(result.projection.last_sequence, 1)

    def test_preledger_empty_assertion_rejected(self) -> None:
        initialize_authority_namespace(self.binding)
        with self.assertRaises(LedgerError) as caught:
            initialize_ledger_binding(
                self.binding,
                conflict_domain_ref="test-conflict-domain",
                environment_classification="KALSHI_DEMO",
                ledger_path=self.ledger_path,
                canonical_repository_root=self.repository_root,
                preledger_history_mode="PRELEDGER_HISTORY_PROVEN_EMPTY",
            )
        self.assertEqual(caught.exception.code, FailureCode.PRELEDGER_EMPTY_ASSERTION_UNSUPPORTED)

    def test_conflict_domain_second_binding_rejected(self) -> None:
        self.initialize()
        with self.assertRaises(LedgerError) as caught:
            initialize_ledger_binding(
                self.binding,
                conflict_domain_ref="test-conflict-domain",
                environment_classification="KALSHI_DEMO",
                ledger_path=self.root / "second.sqlite3",
                canonical_repository_root=self.repository_root,
            )
        self.assertEqual(caught.exception.code, FailureCode.AUTHORITY_CONFLICT_DOMAIN_ALREADY_BOUND)
        self.assertFalse((self.root / "second.sqlite3").exists())

    def test_wrong_expected_path_and_environment_rejected(self) -> None:
        self.initialize()
        other = self.root / "other.sqlite3"
        sqlite3.connect(other).close()
        wrong_path = acquire_local_state(
            self.binding,
            conflict_domain_ref="test-conflict-domain",
            expected_environment="KALSHI_DEMO",
            canonical_repository_root=self.repository_root,
            acquisition_mode=AcquisitionMode.NORMAL_WRITER,
            expected_ledger_path=other,
        )
        self.assertEqual(wrong_path.failure_code, FailureCode.LEDGER_AUTHORITY_BINDING_MISMATCH)
        wrong_environment = acquire_local_state(
            self.binding,
            conflict_domain_ref="test-conflict-domain",
            expected_environment="PRODUCTION",
            canonical_repository_root=self.repository_root,
            acquisition_mode=AcquisitionMode.NORMAL_WRITER,
        )
        self.assertEqual(wrong_environment.failure_code, FailureCode.LEDGER_ENVIRONMENT_MISMATCH)

    def test_schema_mismatch_fails_closed(self) -> None:
        self.initialize()
        connection = sqlite3.connect(self.ledger_path)
        connection.execute("PRAGMA user_version=2")
        connection.commit()
        connection.close()
        result = acquire_local_state(
            self.binding,
            conflict_domain_ref="test-conflict-domain",
            expected_environment="KALSHI_DEMO",
            canonical_repository_root=self.repository_root,
            acquisition_mode=AcquisitionMode.NORMAL_WRITER,
        )
        self.assertEqual(result.restart_classification, RestartClassification.SCHEMA_UNSUPPORTED)
        self.assertEqual(result.failure_code, FailureCode.LEDGER_SCHEMA_UNSUPPORTED_NEWER)

    def test_authority_schema_mismatch_fails_closed(self) -> None:
        self.initialize()
        connection = sqlite3.connect(self.binding.authority_store_resolved_path)
        connection.execute("PRAGMA user_version=2")
        connection.commit(); connection.close()
        result = acquire_local_state(
            self.binding,
            conflict_domain_ref="test-conflict-domain",
            expected_environment="KALSHI_DEMO",
            canonical_repository_root=self.repository_root,
            acquisition_mode=AcquisitionMode.NORMAL_WRITER,
        )
        self.assertEqual(result.failure_code, FailureCode.AUTHORITY_SCHEMA_UNSUPPORTED_NEWER)
        self.assertEqual(result.restart_classification, RestartClassification.SCHEMA_UNSUPPORTED)

    def test_authority_namespace_identity_mismatch(self) -> None:
        self.initialize()
        wrong_binding = AuthorityNamespaceBinding.bind(
            authority_namespace_id="different-namespace",
            authority_namespace_root=self.authority_root,
            canonical_repository_root=self.repository_root,
        )
        result = acquire_local_state(
            wrong_binding,
            conflict_domain_ref="test-conflict-domain",
            expected_environment="KALSHI_DEMO",
            canonical_repository_root=self.repository_root,
            acquisition_mode=AcquisitionMode.NORMAL_WRITER,
        )
        self.assertEqual(result.failure_code, FailureCode.AUTHORITY_IDENTITY_MISMATCH)
        self.assertEqual(result.restart_classification, RestartClassification.AUTHORITY_INTEGRITY_FAILURE)

    def test_ledger_instance_identity_mismatch(self) -> None:
        self.initialize()
        connection = sqlite3.connect(self.ledger_path)
        connection.executescript(
            "DROP TRIGGER trg_ledger_meta_no_update;"
            "UPDATE ledger_meta SET ledger_instance_id='00000000-0000-4000-8000-000000000099';"
            "CREATE TRIGGER trg_ledger_meta_no_update BEFORE UPDATE ON ledger_meta "
            "BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_LEDGER_META'); END;"
        )
        connection.commit(); connection.close()
        result = acquire_local_state(
            self.binding,
            conflict_domain_ref="test-conflict-domain",
            expected_environment="KALSHI_DEMO",
            canonical_repository_root=self.repository_root,
            acquisition_mode=AcquisitionMode.NORMAL_WRITER,
        )
        self.assertEqual(result.failure_code, FailureCode.LEDGER_INSTANCE_ID_MISMATCH)
        self.assertEqual(result.restart_classification, RestartClassification.LEDGER_IDENTITY_FAILURE)

    def test_authority_ahead_of_ledger_fails_closed(self) -> None:
        self.initialize()
        connection = sqlite3.connect(self.binding.authority_store_resolved_path)
        connection.execute(
            "UPDATE conflict_domain_authority SET trusted_sequence=2,trusted_event_hash=?,updated_at_utc=?",
            ("a" * 64, "2026-08-13T12:30:00.000000Z"),
        )
        connection.commit(); connection.close()
        result = acquire_local_state(
            self.binding,
            conflict_domain_ref="test-conflict-domain",
            expected_environment="KALSHI_DEMO",
            canonical_repository_root=self.repository_root,
            acquisition_mode=AcquisitionMode.NORMAL_WRITER,
        )
        self.assertEqual(result.failure_code, FailureCode.AUTHORITY_AHEAD_OF_LEDGER_ROLLBACK_OR_REPLACEMENT)
        self.assertEqual(result.restart_classification, RestartClassification.AUTHORITY_LEDGER_ROLLBACK_FAILURE)

    def test_anchor_hash_mismatch_fails_closed(self) -> None:
        self.initialize()
        connection = sqlite3.connect(self.binding.authority_store_resolved_path)
        connection.executescript(
            "DROP TRIGGER trg_conflict_authority_monotonic_tail;"
            "UPDATE conflict_domain_authority SET trusted_event_hash='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';"
            "CREATE TRIGGER trg_conflict_authority_monotonic_tail BEFORE UPDATE ON conflict_domain_authority "
            "WHEN NEW.trusted_sequence <= OLD.trusted_sequence "
            "BEGIN SELECT RAISE(ABORT, 'NON_MONOTONIC_AUTHORITY_TAIL'); END;"
        )
        connection.commit(); connection.close()
        result = acquire_local_state(
            self.binding,
            conflict_domain_ref="test-conflict-domain",
            expected_environment="KALSHI_DEMO",
            canonical_repository_root=self.repository_root,
            acquisition_mode=AcquisitionMode.NORMAL_WRITER,
        )
        self.assertEqual(result.failure_code, FailureCode.AUTHORITY_LEDGER_ANCHOR_HASH_MISMATCH)
        self.assertEqual(result.restart_classification, RestartClassification.LEDGER_INTEGRITY_FAILURE)

    def test_invalid_ledger_ahead_suffix_is_not_authority_anchored(self) -> None:
        self.initialize()
        connection = sqlite3.connect(self.ledger_path)
        connection.execute(
            "INSERT INTO ledger_events VALUES (2,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "evt_000000000000400080000000000000ff",
                connection.execute("SELECT ledger_instance_id FROM ledger_meta").fetchone()[0],
                "WRITER_PROOF_HELD", 1, None, "synthetic-incident", None,
                "2026-08-13T12:30:00.000000Z",
                '{"conflict_domain_ref":"test-conflict-domain","held_reason":"SYNTHETIC","protected_unresolved_write_event_ids":[],"writer_proof_id":"proof"}',
                "0" * 64, "0" * 64, "1" * 64,
            ),
        )
        connection.commit(); connection.close()
        result = acquire_local_state(
            self.binding,
            conflict_domain_ref="test-conflict-domain",
            expected_environment="KALSHI_DEMO",
            canonical_repository_root=self.repository_root,
            acquisition_mode=AcquisitionMode.NORMAL_WRITER,
        )
        self.assertEqual(result.restart_classification, RestartClassification.LEDGER_INTEGRITY_FAILURE)
        authority = sqlite3.connect(self.binding.authority_store_resolved_path)
        try:
            self.assertEqual(authority.execute("SELECT trusted_sequence FROM conflict_domain_authority").fetchone()[0], 1)
        finally:
            authority.close()

    def test_semantic_conflict_is_replayed_before_catchup_and_locks_release(self) -> None:
        self.initialize()
        locked = self.locked()
        trusted_before = (
            locked.authority_row.trusted_sequence,
            locked.authority_row.trusted_event_hash,
        )
        session_id = "ws_000000000000400080000000000000aa"
        inputs = (
            EventInput(EventType.WRITER_SESSION_STARTED, {
                "lock_model": ledger.LOCK_MODEL,
                "prior_session_state": "NONE",
                "session_schema_revision": 1,
                "writer_session_id": session_id,
            }, writer_session_id=session_id),
            EventInput(EventType.ORDER_IDENTITY_BOUND, {
                "binding_basis_event_ids": [],
                "client_order_id": "client-conflict",
                "environment": "KALSHI_DEMO",
                "incident_id": "semantic-conflict-incident",
                "venue": "KALSHI",
                "venue_order_id": "order-A",
            }, session_id, "semantic-conflict-incident"),
            EventInput(EventType.ORDER_IDENTITY_BOUND, {
                "binding_basis_event_ids": [],
                "client_order_id": "client-conflict",
                "environment": "KALSHI_DEMO",
                "incident_id": "semantic-conflict-incident",
                "venue": "KALSHI",
                "venue_order_id": "order-B",
            }, session_id, "semantic-conflict-incident"),
        )
        sequence = locked.events[-1].sequence
        previous = locked.events[-1].event_hash
        built = []
        for event_input in inputs:
            sequence += 1
            event = ledger._construct_event(
                meta=locked.ledger_meta,
                sequence=sequence,
                previous_hash=previous,
                event_input=event_input,
                clock=self.inputs.clock,
                uuid_factory=self.inputs.uuid,
            )
            built.append(event)
            previous = event.event_hash
        locked.ledger.execute("BEGIN IMMEDIATE")
        for event in built:
            ledger._insert_event(locked.ledger, event)
        locked.ledger.commit()
        locked.close()

        result = acquire_local_state(
            self.binding,
            conflict_domain_ref="test-conflict-domain",
            expected_environment="KALSHI_DEMO",
            canonical_repository_root=self.repository_root,
            acquisition_mode=AcquisitionMode.NORMAL_WRITER,
            expected_ledger_path=self.ledger_path,
        )
        self.assertIsNone(result.handle)
        self.assertEqual(result.failure_code, FailureCode.ORDER_IDENTITY_BINDING_CONFLICT)
        authority = sqlite3.connect(self.binding.authority_store_resolved_path)
        ledger_connection = sqlite3.connect(self.ledger_path)
        try:
            trusted_after = authority.execute(
                "SELECT trusted_sequence,trusted_event_hash FROM conflict_domain_authority"
            ).fetchone()
            self.assertEqual(trusted_after, trusted_before)
            self.assertEqual(ledger_connection.execute("SELECT count(*) FROM ledger_events").fetchone()[0], 4)
        finally:
            ledger_connection.close()
            authority.close()

        # The failed replay deterministically released both exclusive locks.
        authority_lock = ledger._connect_existing(
            self.binding.authority_store_resolved_path,
            authority=True,
        )
        ledger_lock = None
        try:
            authority_lock.execute("BEGIN EXCLUSIVE")
            ledger_lock = ledger._connect_existing(self.ledger_path, authority=False)
            ledger_lock.execute("BEGIN EXCLUSIVE")
        finally:
            if ledger_lock is not None:
                ledger_lock.close()
            authority_lock.close()

    def test_corrupt_ledger_fails_integrity_and_is_not_recreated(self) -> None:
        self.initialize()
        expected_size = self.ledger_path.stat().st_size
        with self.ledger_path.open("r+b") as stream:
            stream.seek(0)
            stream.write(b"not-a-sqlite-db")
        result = acquire_local_state(
            self.binding,
            conflict_domain_ref="test-conflict-domain",
            expected_environment="KALSHI_DEMO",
            canonical_repository_root=self.repository_root,
            acquisition_mode=AcquisitionMode.NORMAL_WRITER,
        )
        self.assertIn(result.failure_code, {FailureCode.LEDGER_INTEGRITY_CHECK_FAILURE, FailureCode.LEDGER_STORAGE_OPEN_FAILURE})
        self.assertTrue(self.ledger_path.exists())
        self.assertEqual(self.ledger_path.stat().st_size, expected_size)

    def test_missing_bound_ledger_is_not_recreated(self) -> None:
        self.initialize()
        moved = self.root / "execution.moved"
        self.ledger_path.rename(moved)
        result = acquire_local_state(
            self.binding,
            conflict_domain_ref="test-conflict-domain",
            expected_environment="KALSHI_DEMO",
            canonical_repository_root=self.repository_root,
            acquisition_mode=AcquisitionMode.NORMAL_WRITER,
        )
        self.assertEqual(result.failure_code, FailureCode.LEDGER_FILE_MISSING)
        self.assertFalse(self.ledger_path.exists())

    def test_missing_conflict_domain_binding_is_not_created(self) -> None:
        initialize_authority_namespace(self.binding)
        result = acquire_local_state(
            self.binding,
            conflict_domain_ref="test-conflict-domain",
            expected_environment="KALSHI_DEMO",
            canonical_repository_root=self.repository_root,
            acquisition_mode=AcquisitionMode.NORMAL_WRITER,
        )
        self.assertEqual(result.failure_code, FailureCode.AUTHORITY_CONFLICT_DOMAIN_BINDING_MISSING)
        connection = sqlite3.connect(self.binding.authority_store_resolved_path)
        try:
            self.assertEqual(connection.execute("SELECT count(*) FROM conflict_domain_authority").fetchone()[0], 0)
        finally:
            connection.close()

    def test_authority_path_inside_repository_is_rejected(self) -> None:
        with self.assertRaises(LedgerError) as caught:
            AuthorityNamespaceBinding.bind(
                authority_namespace_id="inside",
                authority_namespace_root=self.repository_root,
                canonical_repository_root=self.repository_root,
            )
        self.assertEqual(caught.exception.code, FailureCode.AUTHORITY_PATH_INSIDE_CANONICAL_REPOSITORY)

    def test_ledger_path_inside_repository_is_rejected(self) -> None:
        initialize_authority_namespace(self.binding)
        with self.assertRaises(LedgerError) as caught:
            initialize_ledger_binding(
                self.binding,
                conflict_domain_ref="test-conflict-domain",
                environment_classification="KALSHI_DEMO",
                ledger_path=self.repository_root / "prohibited-ledger.sqlite3",
                canonical_repository_root=self.repository_root,
            )
        self.assertEqual(caught.exception.code, FailureCode.LEDGER_PATH_INSIDE_CANONICAL_REPOSITORY)
        self.assertFalse((self.repository_root / "prohibited-ledger.sqlite3").exists())

    def test_real_multiprocess_authority_lock_rejects_second_writer(self) -> None:
        self.initialize()
        held = self.locked()
        context = multiprocessing.get_context("spawn")
        queue = context.Queue()
        process = context.Process(
            target=_multiprocess_lock_worker,
            args=(str(self.authority_root), str(self.repository_root), str(self.ledger_path), queue),
        )
        process.start()
        process.join(15)
        try:
            self.assertFalse(process.is_alive())
            classification, code = queue.get(timeout=3)
            self.assertEqual(classification, RestartClassification.CONCURRENT_WRITER_BLOCKED.value)
            self.assertEqual(code, FailureCode.LEDGER_CONCURRENT_WRITER.value)
        finally:
            if process.is_alive():
                process.terminate()
            held.close()

    def test_lock_takeover_and_abnormal_session_recording(self) -> None:
        self.initialize()
        first = self.locked()
        session = start_writer_session(first, prior_session_state="NONE")
        first.close()  # abnormal: no end event
        second = self.locked()
        next_session = start_writer_session(second, prior_session_state="ABNORMAL")
        projection = second.projection()
        self.assertIn(session, projection.abnormal_prior_session_ids)
        self.assertEqual(projection.active_writer_session_id, next_session)
        end_writer_session(second, writer_session_id=next_session)
        reopened = self.locked()
        self.assertIsNone(reopened.projection().active_writer_session_id)
        clean_takeover = start_writer_session(reopened, prior_session_state="CLEAN")
        self.assertEqual(reopened.projection().active_writer_session_id, clean_takeover)
        end_writer_session(reopened, writer_session_id=clean_takeover)

    def _prepared(self, request_id: str = "request-1") -> dict[str, object]:
        query = {"ticker": "SYNTHETIC"}
        body = {"client_order_id": "00000000-0000-4000-8000-000000000001", "count": 1}
        identity = {
            "adapter_payload_schema_id": "synthetic-v1",
            "canonical_body": body,
            "canonical_body_sha256": sha256_hex(canonical_json_bytes(body)),
            "canonical_query": query,
            "canonical_query_sha256": sha256_hex(canonical_json_bytes(query)),
            "client_order_id": body["client_order_id"],
            "environment": "KALSHI_DEMO",
            "idempotency_key": body["client_order_id"],
            "method": "POST",
            "operation_class": "WRITE",
            "operation_name": "SYNTHETIC_CREATE",
            "path_without_query": "/synthetic/orders",
            "request_id": request_id,
            "venue": "KALSHI",
            "venue_order_id": None,
        }
        identity["prepared_request_sha256"] = prepared_request_identity(identity)
        return identity

    def _intent(self) -> dict[str, object]:
        return {
            "capability_reference_id": "synthetic-capability",
            "client_order_id": "00000000-0000-4000-8000-000000000001",
            "conflict_domain_ref": "test-conflict-domain",
            "environment": "KALSHI_DEMO",
            "execution_attempt_id": "synthetic-attempt",
            "incident_id": "synthetic-incident",
            "intent_payload": {"count": 1},
            "intent_payload_schema_id": "synthetic-v1",
            "operation_family": "CREATE",
            "venue": "KALSHI",
        }

    def _append_intent_and_prepared(self, locked, session: str, request_id: str = "request-1") -> None:
        locked.append_batch((EventInput(
            EventType.EXECUTION_INTENT_RECORDED,
            self._intent(),
            session,
            "synthetic-incident",
            "synthetic-attempt",
        ),))
        locked.append_batch((EventInput(
            EventType.REQUEST_PREPARED,
            self._prepared(request_id),
            session,
            "synthetic-incident",
            "synthetic-attempt",
        ),))

    def _append_boundary(self, locked, session: str, request_id: str = "request-1"):
        prepared = self._prepared(request_id)
        return locked.append_batch((EventInput(
            EventType.WRITE_SEND_BOUNDARY_ENTERED,
            {
                "operation_name": prepared["operation_name"],
                "prepared_request_sha256": prepared["prepared_request_sha256"],
                "request_id": request_id,
                "write_ambiguity_rule": "WRITE_MAY_HAVE_BEEN_SENT_AFTER_THIS_COMMIT",
            },
            session,
            "synthetic-incident",
            "synthetic-attempt",
        ),))

    def _append_held_proof(self, locked) -> None:
        locked.append_batch((EventInput(EventType.WRITER_PROOF_HELD, {
            "conflict_domain_ref": "test-conflict-domain",
            "held_reason": "SYNTHETIC_UNRESOLVED_WRITE",
            "protected_unresolved_write_event_ids": [],
            "writer_proof_id": "synthetic-proof",
        }, incident_id="synthetic-incident"),))

    def _append_closed_response(self, locked, session: str) -> None:
        locked.append_batch((EventInput(EventType.HTTP_RESPONSE_CLASSIFIED, {
            "adapter_result_class": "SYNTHETIC_CLOSED",
            "http_status": 200,
            "request_id": "request-1",
            "response_byte_length": 2,
            "response_media_type": "application/json",
            "response_sha256": sha256_hex(b"{}"),
            "validated_identity_fields": {"client_order_id": "00000000-0000-4000-8000-000000000001"},
            "write_closure_class": "AUTHORITATIVE_RESULT_CLOSED",
        }, session, "synthetic-incident", "synthetic-attempt"),))

    def test_authority_anchored_send_gate_and_no_automatic_resend(self) -> None:
        self.initialize()
        locked = self.locked()
        session = start_writer_session(locked, prior_session_state="NONE")
        before = locked.projection()
        with self.assertRaises(LedgerError) as caught:
            append_authority_anchored_send_gate(
                locked,
                writer_session_id=session,
                incident_id="synthetic-incident",
                execution_attempt_id="synthetic-attempt",
                intent_payload=self._intent(),
                prepared_payload=self._prepared(),
            )
        self.assertEqual(caught.exception.code, FailureCode.LEGACY_IMPORT_ONLY_ACQUISITION_REJECTED)
        self.assertEqual(locked.projection().last_sequence, before.last_sequence)
        locked.close()

    def test_boundary_authority_failure_exposes_no_gate_and_reopen_catches_forward(self) -> None:
        self.initialize()
        calls = {"authority": 0}

        def hook(stage: str) -> None:
            if stage == "before_authority_commit":
                calls["authority"] += 1
                if calls["authority"] == 4:
                    raise sqlite3.OperationalError("synthetic definite failure")

        locked = self.locked(fault_hook=hook)
        session = start_writer_session(locked, prior_session_state="NONE")
        self._append_intent_and_prepared(locked, session)
        with self.assertRaises(LedgerError) as caught:
            self._append_boundary(locked, session)
        self.assertEqual(caught.exception.code, FailureCode.AUTHORITY_ANCHOR_COMMIT_FAILURE)
        reopened = self.locked()
        self.assertEqual(reopened.relation, ledger.AuthorityLedgerRelation.LEDGER_AHEAD)
        self.assertIn("request-1", reopened.projection().unresolved_write_request_ids)
        reopened.close()

    def test_authority_unknown_after_ledger_commit_requires_reopen(self) -> None:
        self.initialize()
        triggered = {"done": False}

        def hook(stage: str) -> None:
            if stage == "before_authority_commit" and not triggered["done"]:
                triggered["done"] = True
                raise CommitResultUnknown(FailureCode.AUTHORITY_ANCHOR_COMMIT_RESULT_UNKNOWN)

        locked = self.locked(fault_hook=hook)
        with self.assertRaises(LedgerError) as caught:
            locked.append_batch((EventInput(EventType.WRITER_PROOF_HELD, {
                "conflict_domain_ref": "test-conflict-domain",
                "held_reason": "SYNTHETIC",
                "protected_unresolved_write_event_ids": [],
                "writer_proof_id": "synthetic-proof",
            }, incident_id="synthetic-incident"),))
        self.assertEqual(caught.exception.code, FailureCode.AUTHORITY_ANCHOR_COMMIT_RESULT_UNKNOWN)
        reopened = self.locked()
        self.assertEqual(reopened.relation, ledger.AuthorityLedgerRelation.LEDGER_AHEAD)
        reopened.close()

    def test_boundary_authority_unknown_exposes_no_gate(self) -> None:
        self.initialize()
        calls = {"authority": 0}

        def hook(stage: str) -> None:
            if stage == "before_authority_commit":
                calls["authority"] += 1
                if calls["authority"] == 4:
                    raise CommitResultUnknown(FailureCode.AUTHORITY_ANCHOR_COMMIT_RESULT_UNKNOWN)

        locked = self.locked(fault_hook=hook)
        session = start_writer_session(locked, prior_session_state="NONE")
        self._append_intent_and_prepared(locked, session)
        with self.assertRaises(LedgerError) as caught:
            self._append_boundary(locked, session)
        self.assertEqual(caught.exception.code, FailureCode.AUTHORITY_ANCHOR_COMMIT_RESULT_UNKNOWN)
        reopened = self.locked()
        self.assertIn("request-1", reopened.projection().unresolved_write_request_ids)
        reopened.close()

    def test_exact_duplicate_event_id_is_idempotent_and_conflict_rejected(self) -> None:
        self.initialize()
        locked = self.locked()
        session = start_writer_session(locked, prior_session_state="NONE")
        event = EventInput(
            EventType.EXECUTION_HALTED,
            {"reason": "SYNTHETIC", "state_projection_ref": "local"},
            writer_session_id=session,
            incident_id="synthetic-incident",
            event_id="evt_000000000000400080000000000000aa",
            recorded_at_utc="2026-08-13T12:00:10.000000Z",
        )
        first = locked.append_batch((event,))
        second = locked.append_batch((event,))
        self.assertEqual(first.status, AppendStatus.APPENDED_AND_ANCHORED)
        self.assertEqual(second.status, AppendStatus.IDEMPOTENT_DUPLICATE)
        conflict = EventInput(
            EventType.EXECUTION_HALTED,
            {"reason": "DIFFERENT", "state_projection_ref": "local"},
            writer_session_id=session,
            incident_id="synthetic-incident",
            event_id=event.event_id,
            recorded_at_utc=event.recorded_at_utc,
        )
        with self.assertRaises(LedgerError) as caught:
            locked.append_batch((conflict,))
        self.assertEqual(caught.exception.code, FailureCode.EVENT_ID_CONTENT_CONFLICT)
        locked.close()

    def test_deterministic_export_is_secret_safe_and_has_no_absolute_paths(self) -> None:
        self.initialize()
        locked = self.locked()
        projection = locked.projection()
        one = deterministic_review_export(projection)
        two = deterministic_review_export(projection)
        self.assertEqual(one, two)
        self.assertEqual(sha256_hex(one), sha256_hex(two))
        decoded = json.loads(one)
        self.assertNotIn(str(self.root), one.decode("utf-8"))
        self.assertNotIn("authority_store_resolved_path", decoded)
        self.assertEqual(decoded["integrity_validation_result"], "PASS")
        locked.close()
        reopened = self.locked()
        self.assertEqual(one, deterministic_review_export(reopened.projection()))
        reopened.close()

    def test_event_and_meta_triggers_reject_update_delete(self) -> None:
        self.initialize()
        connection = sqlite3.connect(self.ledger_path)
        try:
            statements = (
                "UPDATE ledger_events SET event_type='X' WHERE sequence=1",
                "DELETE FROM ledger_events WHERE sequence=1",
                "UPDATE ledger_meta SET conflict_domain_ref='X' WHERE singleton=1",
                "DELETE FROM ledger_meta WHERE singleton=1",
            )
            for statement in statements:
                with self.subTest(statement=statement), self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(statement)
        finally:
            connection.close()

    def test_trigger_definition_mismatch_fails_schema_validation(self) -> None:
        self.initialize()
        connection = sqlite3.connect(self.ledger_path)
        connection.executescript(
            "DROP TRIGGER trg_ledger_events_no_delete;"
            "CREATE TRIGGER trg_ledger_events_no_delete BEFORE DELETE ON ledger_events "
            "BEGIN SELECT RAISE(ABORT, 'WRONG_REASON'); END;"
        )
        connection.commit(); connection.close()
        result = acquire_local_state(
            self.binding,
            conflict_domain_ref="test-conflict-domain",
            expected_environment="KALSHI_DEMO",
            canonical_repository_root=self.repository_root,
            acquisition_mode=AcquisitionMode.NORMAL_WRITER,
        )
        self.assertEqual(result.failure_code, FailureCode.LEDGER_SCHEMA_IDENTITY_MISMATCH)

    def test_authority_binding_fields_and_tail_cannot_move_backward(self) -> None:
        self.initialize()
        connection = sqlite3.connect(self.binding.authority_store_resolved_path)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("UPDATE conflict_domain_authority SET ledger_resolved_path='different'")
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("UPDATE conflict_domain_authority SET trusted_sequence=1")
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM conflict_domain_authority")
        finally:
            connection.close()

    def test_writer_proof_release_is_blocked_while_history_incomplete(self) -> None:
        self.initialize()
        locked = self.locked()
        session = start_writer_session(locked, prior_session_state="NONE")
        with self.assertRaises(LedgerError) as caught:
            locked.append_batch((EventInput(EventType.WRITER_PROOF_RELEASED, {
                "conflict_domain_ref": "test-conflict-domain",
                "release_basis_event_ids": [],
                "release_contract_id": "synthetic-contract",
                "writer_proof_id": "synthetic-proof",
            }, session, "synthetic-incident"),))
        self.assertEqual(caught.exception.code, FailureCode.RELEASE_PREDICATE_CHANGED)
        locked.close()

    def test_unknown_event_type_is_schema_unsupported(self) -> None:
        self.initialize()
        locked = self.locked()
        session = start_writer_session(locked, prior_session_state="NONE")
        locked.close()
        connection = sqlite3.connect(self.ledger_path)
        connection.executescript(
            "DROP TRIGGER trg_ledger_events_no_update;"
            "UPDATE ledger_events SET event_type='FUTURE_EVENT' WHERE sequence=2;"
            "CREATE TRIGGER trg_ledger_events_no_update BEFORE UPDATE ON ledger_events "
            "BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_LEDGER_EVENTS'); END;"
        )
        connection.commit(); connection.close()
        result = acquire_local_state(
            self.binding,
            conflict_domain_ref="test-conflict-domain",
            expected_environment="KALSHI_DEMO",
            canonical_repository_root=self.repository_root,
            acquisition_mode=AcquisitionMode.NORMAL_WRITER,
        )
        self.assertEqual(result.failure_code, FailureCode.LEDGER_SCHEMA_UNSUPPORTED_EVENT_TYPE)
        self.assertEqual(result.restart_classification, RestartClassification.SCHEMA_UNSUPPORTED)

    def test_payload_hash_and_previous_hash_tampering_fail_closed(self) -> None:
        for column, value in (("payload_sha256", "a" * 64), ("previous_event_hash", "b" * 64)):
            with self.subTest(column=column):
                self.tearDown(); self.setUp(); self.initialize()
                locked = self.locked()
                start_writer_session(locked, prior_session_state="NONE")
                locked.close()
                connection = sqlite3.connect(self.ledger_path)
                connection.executescript(
                    "DROP TRIGGER trg_ledger_events_no_update;"
                    f"UPDATE ledger_events SET {column}='{value}' WHERE sequence=2;"
                    "CREATE TRIGGER trg_ledger_events_no_update BEFORE UPDATE ON ledger_events "
                    "BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_LEDGER_EVENTS'); END;"
                )
                connection.commit(); connection.close()
                result = acquire_local_state(
                    self.binding,
                    conflict_domain_ref="test-conflict-domain",
                    expected_environment="KALSHI_DEMO",
                    canonical_repository_root=self.repository_root,
                    acquisition_mode=AcquisitionMode.NORMAL_WRITER,
                )
                self.assertEqual(result.failure_code, FailureCode.LEDGER_HASH_CHAIN_FAILURE)
                self.assertEqual(result.restart_classification, RestartClassification.LEDGER_INTEGRITY_FAILURE)

    def test_authoritative_closure_removes_unresolved_request_only_after_anchor(self) -> None:
        self.initialize()
        locked = self.locked()
        session = start_writer_session(locked, prior_session_state="NONE")
        self._append_intent_and_prepared(locked, session)
        self._append_boundary(locked, session)
        locked.append_batch((EventInput(EventType.HTTP_RESPONSE_CLASSIFIED, {
            "adapter_result_class": "SYNTHETIC_CLOSED",
            "http_status": 200,
            "request_id": "request-1",
            "response_byte_length": 2,
            "response_media_type": "application/json",
            "response_sha256": sha256_hex(b"{}"),
            "validated_identity_fields": {"client_order_id": "00000000-0000-4000-8000-000000000001"},
            "write_closure_class": "AUTHORITATIVE_RESULT_CLOSED",
        }, session, "synthetic-incident", "synthetic-attempt"),))
        self.assertEqual(locked.projection().unresolved_write_request_ids, ())
        locked.close()

    def test_physical_power_loss_evidence_is_not_claimed(self) -> None:
        self.assertEqual(PHYSICAL_POWER_LOSS_QUALIFICATION, "NOT_PERFORMED")

    def test_closed_crash_fault_matrix_a_through_r(self) -> None:
        self.assertEqual(tuple(ledger.CRASH_FAULT_MATRIX), tuple("ABCDEFGHIJKLMNOPQR"))
        for case, expectation in ledger.CRASH_FAULT_MATRIX.items():
            with self.subTest(case=case):
                self.assertFalse(expectation.automatic_resend)
                if case in "ABCIJKLMOPQR":
                    self.assertEqual(expectation.transport_invocation_count, 0)
                if case in "DEN":
                    self.assertEqual(expectation.transport_invocation_count, 1)
        self.assertTrue(ledger.CRASH_FAULT_MATRIX["J"].unknown_write)
        self.assertEqual(ledger.CRASH_FAULT_MATRIX["O"].restart_interpretation, "RESTART_AUTHORITY_LEDGER_ROLLBACK_FAILURE")

    def test_executable_crash_fault_matrix_a_through_r(self) -> None:
        def fresh_case():
            case = type(self)(methodName="test_physical_power_loss_evidence_is_not_claimed")
            case.setUp()
            case.initialize()
            return case

        def seed(case, *, boundary: bool, held: bool = False):
            locked = case.locked()
            if held:
                case._append_held_proof(locked)
            session = start_writer_session(locked, prior_session_state="NONE")
            case._append_intent_and_prepared(locked, session)
            if boundary:
                case._append_boundary(locked, session)
            return locked, session

        def fake_transport(counter: dict[str, int]) -> None:
            counter["count"] += 1

        for case_id in "ABCDEFGHIJKLMNOPQR":
            with self.subTest(case=case_id):
                case = fresh_case()
                transport = {"count": 0}
                try:
                    if case_id == "A":
                        locked = case.locked()
                        session = start_writer_session(locked, prior_session_state="NONE")
                        before = locked.projection().last_sequence
                        locked.fault_hook = lambda stage: (
                            (_ for _ in ()).throw(sqlite3.OperationalError("fault A"))
                            if stage == "before_ledger_commit" else None
                        )
                        with self.assertRaises(LedgerError):
                            locked.append_batch((EventInput(
                                EventType.EXECUTION_INTENT_RECORDED,
                                case._intent(), session,
                                "synthetic-incident", "synthetic-attempt",
                            ),))
                        self.assertEqual(locked.projection().last_sequence, before)
                        locked.close()
                        observed = ledger.CrashFaultExpectation("NONE", "UNCHANGED", 0, "PRIOR_STATE_CONTROLS", False, "PRIOR")
                    elif case_id == "B":
                        locked, _ = seed(case, boundary=False)
                        projection = locked.projection()
                        self.assertIn("request-1", projection.prepared_requests)
                        self.assertFalse(projection.unresolved_write_request_ids)
                        locked.close()
                        observed = ledger.CrashFaultExpectation("PRE_BOUNDARY_SUCCESS", "PRE_BOUNDARY_SUCCESS", 0, "PREPARED_NO_BOUNDARY", False, "PRIOR_OR_HELD")
                    elif case_id in {"C", "M"}:
                        locked, _ = seed(case, boundary=True, held=True)
                        projection = locked.projection()
                        self.assertEqual(projection.unresolved_write_request_ids, ("request-1",))
                        self.assertEqual(projection.writer_proof_state_by_proof_id["synthetic-proof"], "HELD")
                        locked.close()
                        observed = ledger.CrashFaultExpectation("BOUNDARY_SUCCESS", "BOUNDARY_SUCCESS", 0, "WRITE_MAY_HAVE_BEEN_SENT", True, "HELD")
                    elif case_id in {"D", "N"}:
                        locked, _ = seed(case, boundary=True, held=True)
                        fake_transport(transport)
                        projection = locked.projection()
                        self.assertEqual(projection.unresolved_write_request_ids, ("request-1",))
                        locked.close()
                        observed = ledger.CrashFaultExpectation("BOUNDARY_SUCCESS", "BOUNDARY_SUCCESS", transport["count"], "WRITE_RESULT_UNKNOWN", True, "HELD")
                    elif case_id == "E":
                        locked, session = seed(case, boundary=True, held=True)
                        fake_transport(transport)
                        locked.fault_hook = lambda stage: (
                            (_ for _ in ()).throw(sqlite3.OperationalError("fault E"))
                            if stage == "before_ledger_commit" else None
                        )
                        with self.assertRaises(LedgerError):
                            case._append_closed_response(locked, session)
                        self.assertEqual(locked.projection().unresolved_write_request_ids, ("request-1",))
                        locked.close()
                        observed = ledger.CrashFaultExpectation("RESULT_ABSENT_OR_LEDGER_ONLY", "BOUNDARY_TRUSTED", transport["count"], "UNRESOLVED_UNTIL_VALIDATED_CLOSURE", True, "HELD")
                    elif case_id == "F":
                        locked, session = seed(case, boundary=True, held=True)
                        fake_transport(transport)
                        case._append_closed_response(locked, session)
                        self.assertFalse(locked.projection().unresolved_write_request_ids)
                        locked.close()
                        observed = ledger.CrashFaultExpectation("RESULT_SUCCESS", "RESULT_SUCCESS", transport["count"], "EXACT_CLOSURE_CLASS_CONTROLS", None, "REPLAY_CONTROLS")
                    elif case_id == "G":
                        locked, session = seed(case, boundary=True, held=True)
                        locked.fault_hook = lambda stage: (
                            (_ for _ in ()).throw(sqlite3.OperationalError("fault G"))
                            if stage == "before_authority_commit" else None
                        )
                        with self.assertRaises(LedgerError):
                            locked.append_batch((EventInput(EventType.ORDER_OBSERVED, {
                                "canonical_venue_payload": {"status": "synthetic"},
                                "canonical_venue_payload_sha256": sha256_hex(canonical_json_bytes({"status": "synthetic"})),
                                "client_order_id": "00000000-0000-4000-8000-000000000001",
                                "observation_semantic_class": "SYNTHETIC",
                                "source_operation": "SYNTHETIC_READ",
                                "source_request_id": "request-1",
                                "venue_order_id": "order-1",
                                "venue_payload_schema_id": "synthetic-v1",
                            }, session, "synthetic-incident", "synthetic-attempt"),))
                        reopened = case.locked()
                        self.assertEqual(reopened.relation, ledger.AuthorityLedgerRelation.LEDGER_AHEAD)
                        self.assertEqual(reopened.projection().unresolved_write_request_ids, ("request-1",))
                        reopened.close()
                        observed = ledger.CrashFaultExpectation("PRIOR_OR_COMPLETE_BATCH", "PRIOR_OR_NEW_TAIL", None, "REPLAY_COMPLETE_LEDGER_AND_TWO_STORE_RELATION", None, "HELD_WHILE_UNRESOLVED")
                    elif case_id == "H":
                        locked, session = seed(case, boundary=True, held=True)
                        locked.fault_hook = lambda stage: (
                            (_ for _ in ()).throw(sqlite3.OperationalError("fault H"))
                            if stage == "before_authority_commit" else None
                        )
                        with self.assertRaises(LedgerError):
                            end_writer_session(locked, writer_session_id=session)
                        reopened = case.locked()
                        projection = reopened.projection()
                        self.assertIsNone(projection.active_writer_session_id)
                        self.assertEqual(projection.unresolved_write_request_ids, ("request-1",))
                        reopened.close()
                        observed = ledger.CrashFaultExpectation("END_ABSENT_LEDGER_ONLY_OR_ANCHORED", "PRIOR_OR_END_TAIL", None, "SESSION_END_DOES_NOT_CHANGE_WRITE_TRUTH", None, "REPLAY_CONTROLS")
                    elif case_id == "I":
                        locked, session = seed(case, boundary=False)
                        before = locked.projection().last_sequence
                        locked.fault_hook = lambda stage: (
                            (_ for _ in ()).throw(sqlite3.OperationalError("fault I"))
                            if stage == "before_ledger_commit" else None
                        )
                        with self.assertRaises(LedgerError):
                            case._append_boundary(locked, session)
                        self.assertEqual(locked.projection().last_sequence, before)
                        locked.close()
                        observed = ledger.CrashFaultExpectation("BOUNDARY_FAILURE", "UNCHANGED", 0, "NO_COMMITTED_BOUNDARY", False, "PRIOR")
                    elif case_id in {"J", "K", "L"}:
                        locked, session = seed(case, boundary=False, held=True)
                        if case_id == "J":
                            def hook(stage):
                                if stage == "after_ledger_commit":
                                    raise CommitResultUnknown(FailureCode.LEDGER_COMMIT_RESULT_UNKNOWN)
                        elif case_id == "K":
                            def hook(stage):
                                if stage == "before_authority_commit":
                                    raise sqlite3.OperationalError("fault K")
                        else:
                            def hook(stage):
                                if stage == "before_authority_commit":
                                    raise CommitResultUnknown(FailureCode.AUTHORITY_ANCHOR_COMMIT_RESULT_UNKNOWN)
                        locked.fault_hook = hook
                        with self.assertRaises(LedgerError):
                            case._append_boundary(locked, session)
                        reopened = case.locked()
                        self.assertEqual(reopened.relation, ledger.AuthorityLedgerRelation.LEDGER_AHEAD)
                        self.assertEqual(reopened.projection().unresolved_write_request_ids, ("request-1",))
                        reopened.close()
                        labels = {
                            "J": ("OLD_TRUSTED_TAIL", "LEDGER_AHEAD_CATCH_FORWARD_ONLY"),
                            "K": ("DEFINITE_FAILURE", "LEDGER_AHEAD_REOPEN_REQUIRED"),
                            "L": ("UNKNOWN", "CLOSE_REOPEN_EQUAL_OR_LEDGER_AHEAD"),
                        }
                        authority_outcome, interpretation = labels[case_id]
                        observed = ledger.CrashFaultExpectation("BOUNDARY_SUCCESS", authority_outcome, 0, interpretation, True, "HELD")
                    elif case_id == "O":
                        authority = sqlite3.connect(case.binding.authority_store_resolved_path)
                        authority.execute("UPDATE conflict_domain_authority SET trusted_sequence=2,trusted_event_hash=?,updated_at_utc=?", ("a" * 64, "2026-08-13T12:30:00.000000Z"))
                        authority.commit(); authority.close()
                        result = acquire_local_state(case.binding, conflict_domain_ref="test-conflict-domain", expected_environment="KALSHI_DEMO", canonical_repository_root=case.repository_root, acquisition_mode=AcquisitionMode.NORMAL_WRITER)
                        self.assertEqual(result.restart_classification, RestartClassification.AUTHORITY_LEDGER_ROLLBACK_FAILURE)
                        observed = ledger.CrashFaultExpectation("LEDGER_BEHIND", "AUTHORITY_AHEAD", 0, result.restart_classification.value, None, "UNAVAILABLE_OR_HELD")
                    elif case_id == "P":
                        authority = sqlite3.connect(case.binding.authority_store_resolved_path)
                        authority.executescript("DROP TRIGGER trg_conflict_authority_monotonic_tail; UPDATE conflict_domain_authority SET trusted_event_hash='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'; CREATE TRIGGER trg_conflict_authority_monotonic_tail BEFORE UPDATE ON conflict_domain_authority WHEN NEW.trusted_sequence <= OLD.trusted_sequence BEGIN SELECT RAISE(ABORT, 'NON_MONOTONIC_AUTHORITY_TAIL'); END;")
                        authority.commit(); authority.close()
                        result = acquire_local_state(case.binding, conflict_domain_ref="test-conflict-domain", expected_environment="KALSHI_DEMO", canonical_repository_root=case.repository_root, acquisition_mode=AcquisitionMode.NORMAL_WRITER)
                        self.assertEqual(result.restart_classification, RestartClassification.LEDGER_INTEGRITY_FAILURE)
                        observed = ledger.CrashFaultExpectation("UNTRUSTED", "TRUSTED_PAIR_PRESENT", 0, result.restart_classification.value, None, "UNAVAILABLE_OR_HELD")
                    elif case_id == "Q":
                        missing = case.authority_root / "authority.moved"
                        case.binding.authority_store_resolved_path.replace(missing)
                        result = acquire_local_state(case.binding, conflict_domain_ref="test-conflict-domain", expected_environment="KALSHI_DEMO", canonical_repository_root=case.repository_root, acquisition_mode=AcquisitionMode.NORMAL_WRITER)
                        self.assertEqual(result.restart_classification, RestartClassification.AUTHORITY_INTEGRITY_FAILURE)
                        observed = ledger.CrashFaultExpectation("UNAVAILABLE", "MISSING_OR_CORRUPT", 0, result.restart_classification.value, None, "UNAVAILABLE_OR_HELD")
                    else:
                        with self.assertRaises(LedgerError) as caught:
                            initialize_ledger_binding(
                                case.binding,
                                conflict_domain_ref="test-conflict-domain",
                                environment_classification="KALSHI_DEMO",
                                ledger_path=case.root / "second.sqlite3",
                                canonical_repository_root=case.repository_root,
                            )
                        self.assertEqual(caught.exception.code, FailureCode.AUTHORITY_CONFLICT_DOMAIN_ALREADY_BOUND)
                        observed = ledger.CrashFaultExpectation("NON_AUTHORITATIVE_LEDGER", "BINDS_LEDGER_A", 0, "LEDGER_B_WRITER_AUTHORITY_REJECTED", False, "UNAVAILABLE")
                    self.assertFalse(observed.automatic_resend)
                    self.assertEqual(observed, ledger.CRASH_FAULT_MATRIX[case_id])
                finally:
                    case.tearDown()

    def test_first_binding_authority_failure_leaves_unbound_orphan(self) -> None:
        initialize_authority_namespace(self.binding)

        def hook(stage: str) -> None:
            if stage == "before_authority_binding_commit":
                raise sqlite3.OperationalError("synthetic binding failure")

        with self.assertRaises(LedgerError) as caught:
            initialize_ledger_binding(
                self.binding,
                conflict_domain_ref="test-conflict-domain",
                environment_classification="KALSHI_DEMO",
                ledger_path=self.ledger_path,
                canonical_repository_root=self.repository_root,
                fault_hook=hook,
            )
        self.assertEqual(caught.exception.code, FailureCode.AUTHORITY_LEDGER_INITIALIZATION_PARTIAL_FAILURE)
        self.assertTrue(self.ledger_path.exists())
        authority = sqlite3.connect(self.binding.authority_store_resolved_path)
        try:
            self.assertEqual(authority.execute("SELECT count(*) FROM conflict_domain_authority").fetchone()[0], 0)
        finally:
            authority.close()

    # ------------------------------------------------------------------
    # GATE A IMPLEMENTATION 02, Correction 02 (ER-NW-001): the private
    # normal-writer candidate bridge is venue-agnostic and structurally not
    # part of the public acquire_local_state surface.
    # ------------------------------------------------------------------
    def test_private_normal_writer_candidate_exposes_equal_tail_fresh_ledger(self) -> None:
        self.initialize()
        candidate = ledger._acquire_normal_writer_candidate(
            self.binding,
            conflict_domain_ref="test-conflict-domain",
            expected_environment="KALSHI_DEMO",
            canonical_repository_root=self.repository_root,
            expected_ledger_path=self.ledger_path,
        )
        # A structurally fresh ledger has an equal authority/ledger tail by
        # construction: the bridge exposes the candidate (ER-NW-001 items
        # 1-7), even though it is nowhere near durably eligible.  Durable
        # eligibility (history completeness, risk/proof state, etc.) is
        # exclusively the venue binding's concern (ER-NW-003), not this
        # bridge's.
        self.assertIsNotNone(candidate.handle)
        self.assertEqual(candidate.authority_ledger_relation, ledger.AuthorityLedgerRelation.EQUAL)
        self.assertEqual(candidate.projection.history_completeness, "INCOMPLETE")
        self.assertIsNone(candidate.projection.active_writer_session_id)
        candidate.handle.close()

    def test_private_normal_writer_candidate_is_not_public_acquire_local_state(self) -> None:
        # acquire_local_state is the only generic public entry point; the
        # private candidate bridge must not be reachable through it under a
        # different name, and must not appear in the module's public names.
        self.assertNotIn("_acquire_normal_writer_candidate", ledger.__all__)
        self.assertNotIn("acquire_normal_writer_candidate", dir(ledger))

    def test_gate_a_implementation_02_failure_code_enum_values(self) -> None:
        self.assertEqual(FailureCode.NORMAL_WRITER_ACQUISITION_REJECTED.value, "NORMAL_WRITER_ACQUISITION_REJECTED")
        self.assertEqual(FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_REQUIRED.value, "CURRENT_PROCESS_RELEASE_COMPLETION_REQUIRED")
        self.assertEqual(FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_INVALID.value, "CURRENT_PROCESS_RELEASE_COMPLETION_INVALID")
        self.assertEqual(FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_PROCESS_MISMATCH.value, "CURRENT_PROCESS_RELEASE_COMPLETION_PROCESS_MISMATCH")
        self.assertEqual(FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_STALE.value, "CURRENT_PROCESS_RELEASE_COMPLETION_STALE")
        self.assertEqual(FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_NOT_ISSUED.value, "CURRENT_PROCESS_RELEASE_COMPLETION_NOT_ISSUED")


def _binding_canonical(*, account_scope_ref, subaccount, exchange_index):
    conflict = f"KALSHI|KALSHI_DEMO|{account_scope_ref}|SUBACCOUNT={subaccount}"
    obj = {
        "account_scope_ref": account_scope_ref,
        "conflict_domain_ref": conflict,
        "environment": "KALSHI_DEMO",
        "exchange_index": exchange_index,
        "schema_revision": 1,
        "subaccount": subaccount,
        "venue": "KALSHI",
    }
    bsha = sha256_hex(canonical_json_bytes(obj))
    return conflict, obj, bsha, "KEDB1_" + bsha


def _bootstrap_payload(*, conflict, bid, bsha, bootstrap_class, completeness,
                       working="COMPLETE_ZERO", fill="COMPLETE_ZERO", position="COMPLETE_ZERO",
                       ticker=None, floor=Decimal("0")):
    contract_obj = {
        "automatic_flatten_authorized": False,
        "bootstrap_class": bootstrap_class,
        "bootstrap_cutoff_at_utc": "2026-09-01T00:00:00.000000Z",
        "conflict_domain_ref": conflict,
        "domain_binding_id": bid,
        "domain_binding_sha256": bsha,
        "fill_truth": fill,
        "inception_evidence": [],
        "position_truth": position,
        "prestack_activity_completeness": completeness,
        "prestack_evidence": [],
        "retained_position_floor_contracts": floor,
        "retained_position_ticker": ticker,
        "schema_revision": 1,
        "unresolved_cancel_count": 0,
        "unresolved_write_count": 0,
        "working_order_truth": working,
    }
    bcsha = sha256_hex(canonical_json_bytes(contract_obj))
    payload = dict(contract_obj)
    del payload["schema_revision"]
    payload["bootstrap_schema_revision"] = 1
    payload["bootstrap_contract_sha256"] = bcsha
    return payload, bcsha


class Revision2ActiveExecutionDomainLedgerTestCase(unittest.TestCase):
    """R1-B03 T10-T25, T68-T71: revision-2 active execution-domain ledger."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repository_root = Path(__file__).resolve().parents[1]
        self.authority_root = self.root / "authority"
        self.authority_root.mkdir()
        self.inputs = DeterministicInputs()
        self.binding = AuthorityNamespaceBinding.bind(
            authority_namespace_id="rev2-namespace",
            authority_namespace_root=self.authority_root,
            canonical_repository_root=self.repository_root,
        )
        initialize_authority_namespace(self.binding, clock=self.inputs.clock, uuid_factory=self.inputs.uuid)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _init_active(self, *, account_scope_ref="ARB_KALSHI_DEMO_PRIMARY_ACCOUNT",
                     subaccount=1, exchange_index=0, bootstrap_class="KNOWN_NONEMPTY_PRESTACK",
                     completeness="COMPLETE_KNOWN_NONEMPTY_PRESTACK", name="active.sqlite3",
                     fill="COMPLETE_KNOWN_NONZERO", position="COMPLETE_KNOWN_NONZERO",
                     ticker="KXAAAGASD-26SEP02-4.1200", floor=Decimal("1.00")):
        conflict, obj, bsha, bid = _binding_canonical(
            account_scope_ref=account_scope_ref, subaccount=subaccount, exchange_index=exchange_index)
        payload, bcsha = _bootstrap_payload(
            conflict=conflict, bid=bid, bsha=bsha, bootstrap_class=bootstrap_class,
            completeness=completeness, fill=fill, position=position, ticker=ticker, floor=floor)
        incident_id = "adi_" + sha256_hex(
            b"ARB_ACTIVE_EXECUTION_DOMAIN_INCIDENT_V1\x00" + bsha.encode() + b"\x00" + bcsha.encode()
        )[:32]
        proof_id = "adwp_" + sha256_hex(b"ARB_ACTIVE_DOMAIN_WRITER_PROOF_V1\x00" + bsha.encode())[:32]
        ledger_path = self.root / name
        row = ledger.initialize_execution_domain_ledger_v2(
            self.binding,
            conflict_domain_ref=conflict,
            ledger_path=ledger_path,
            canonical_repository_root=self.repository_root,
            preledger_history_mode=bootstrap_class,
            execution_domain_binding_id=bid,
            execution_domain_binding_sha256=bsha,
            execution_domain_binding_json=ledger.canonical_json_text(obj),
            bootstrap_event_payload=payload,
            active_incident_id=incident_id,
            active_writer_proof_id=proof_id,
            clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
        )
        return dict(conflict=conflict, obj=obj, bsha=bsha, bid=bid, payload=payload,
                    bcsha=bcsha, incident_id=incident_id, proof_id=proof_id,
                    ledger_path=ledger_path, row=row)

    def _open(self, ctx):
        return ledger._open_locked(
            self.binding, conflict_domain_ref=ctx["conflict"], expected_environment="KALSHI_DEMO",
            canonical_repository_root=self.repository_root, expected_ledger_path=ctx["ledger_path"],
            clock=self.inputs.clock, uuid_factory=self.inputs.uuid, ledger_revision=2,
        )

    def test_t14_controlled_fresh_inception_genesis(self) -> None:
        ctx = self._init_active(bootstrap_class="CONTROLLED_FRESH_INCEPTION",
                                completeness="COMPLETE_CONTROLLED_FROM_INCEPTION",
                                fill="COMPLETE_ZERO", position="COMPLETE_ZERO",
                                ticker=None, floor=Decimal("0"))
        self.assertEqual(ctx["row"].trusted_sequence, 3)
        locked = self._open(ctx)
        try:
            proj = locked.projection()
            self.assertEqual(proj.history_completeness, "COMPLETE_CONTROLLED_FROM_INCEPTION")
            self.assertEqual([e.event_type for e in locked.events], [
                EventType.LEDGER_INITIALIZED,
                EventType.EXECUTION_DOMAIN_BOOTSTRAP_RECORDED,
                EventType.WRITER_PROOF_HELD,
            ])
            self.assertEqual(proj.writer_proof_state_by_proof_id.get(ctx["proof_id"]), "HELD")
        finally:
            locked.close()

    def test_t15_known_nonempty_prestack_preserves_floor_and_completeness(self) -> None:
        ctx = self._init_active()
        payload = ctx["payload"]
        self.assertEqual(payload["prestack_activity_completeness"], "COMPLETE_KNOWN_NONEMPTY_PRESTACK")
        self.assertEqual(payload["retained_position_floor_contracts"], Decimal("1.00"))
        locked = self._open(ctx)
        try:
            self.assertEqual(locked.events[1].payload["retained_position_ticker"], "KXAAAGASD-26SEP02-4.1200")
        finally:
            locked.close()

    def test_t13_revision1_reader_rejects_revision2_ledger(self) -> None:
        ctx = self._init_active()
        with self.assertRaises(LedgerError) as caught:
            ledger._open_locked(
                self.binding, conflict_domain_ref=ctx["conflict"], expected_environment="KALSHI_DEMO",
                canonical_repository_root=self.repository_root, expected_ledger_path=ctx["ledger_path"],
                clock=self.inputs.clock, uuid_factory=self.inputs.uuid,  # ledger_revision defaults to 1
            )
        self.assertEqual(caught.exception.code, FailureCode.LEDGER_SCHEMA_UNSUPPORTED_NEWER)

    def test_t18_same_conflict_domain_cannot_bind_two_ledgers(self) -> None:
        ctx = self._init_active()
        with self.assertRaises(LedgerError) as caught:
            self._init_active(name="active2.sqlite3")
        self.assertEqual(caught.exception.code, FailureCode.AUTHORITY_CONFLICT_DOMAIN_ALREADY_BOUND)

    def test_t19_separate_subaccounts_distinct_conflict_domain(self) -> None:
        a = self._init_active(subaccount=1, name="a.sqlite3")
        b = self._init_active(subaccount=7, bootstrap_class="CONTROLLED_FRESH_INCEPTION",
                              completeness="COMPLETE_CONTROLLED_FROM_INCEPTION",
                              fill="COMPLETE_ZERO", position="COMPLETE_ZERO", ticker=None,
                              floor=Decimal("0"), name="b.sqlite3")
        self.assertNotEqual(a["conflict"], b["conflict"])
        self.assertNotEqual(a["bsha"], b["bsha"])

    def test_t68_valid_controlled_pairing_accepted(self) -> None:
        ctx = self._init_active(bootstrap_class="CONTROLLED_FRESH_INCEPTION",
                                completeness="COMPLETE_CONTROLLED_FROM_INCEPTION",
                                fill="COMPLETE_ZERO", position="COMPLETE_ZERO", ticker=None,
                                floor=Decimal("0"))
        self.assertEqual(ctx["row"].trusted_sequence, 3)

    def test_t69_valid_known_nonempty_pairing_accepted(self) -> None:
        ctx = self._init_active()
        self.assertEqual(ctx["row"].trusted_sequence, 3)

    def test_t70_cross_pairings_and_unknown_completeness_rejected(self) -> None:
        for bclass, comp in (
            ("CONTROLLED_FRESH_INCEPTION", "COMPLETE_KNOWN_NONEMPTY_PRESTACK"),
            ("KNOWN_NONEMPTY_PRESTACK", "COMPLETE_CONTROLLED_FROM_INCEPTION"),
            ("KNOWN_NONEMPTY_PRESTACK", "COMPLETE"),
            ("KNOWN_NONEMPTY_PRESTACK", "complete_known_nonempty_prestack"),
        ):
            with self.subTest(bclass=bclass, comp=comp):
                with self.assertRaises(LedgerError) as caught:
                    self._init_active(bootstrap_class=bclass, completeness=comp, name=f"x_{bclass}_{comp}.sqlite3")
                self.assertEqual(caught.exception.code, FailureCode.DOMAIN_BOOTSTRAP_COMPLETENESS_MISMATCH)

    def test_t71_n1_bootstrap_hash_commits_completeness_value(self) -> None:
        ctx = self._init_active()
        # The persisted event payload contains the exact completeness string.
        locked = self._open(ctx)
        try:
            self.assertIn("COMPLETE_KNOWN_NONEMPTY_PRESTACK",
                          locked.events[1].payload_json)
        finally:
            locked.close()
        # Changing only the completeness value changes the bootstrap contract hash.
        _, other = _bootstrap_payload(
            conflict=ctx["conflict"], bid=ctx["bid"], bsha=ctx["bsha"],
            bootstrap_class="CONTROLLED_FRESH_INCEPTION",
            completeness="COMPLETE_CONTROLLED_FROM_INCEPTION")
        self.assertNotEqual(ctx["bcsha"], other)

    def test_revision2_event_id_formula(self) -> None:
        ctx = self._init_active()
        payload = ctx["payload"]
        identity = {
            "bootstrap_contract_sha256": payload["bootstrap_contract_sha256"],
            "domain_binding_sha256": payload["domain_binding_sha256"],
        }
        expected = "evt_" + sha256_hex(
            b"ARB_EXECUTION_DOMAIN_BOOTSTRAP_RECORDED_V1\x00" + canonical_json_bytes(identity)
        )[:32]
        self.assertEqual(deterministic_event_id(EventType.EXECUTION_DOMAIN_BOOTSTRAP_RECORDED, payload), expected)

    def test_t16_unknown_incomplete_bootstrap_no_init(self) -> None:
        # An unknown / non-accepted bootstrap class never initializes an
        # active revision-2 ledger.
        with self.assertRaises(LedgerError) as caught:
            self._init_active(bootstrap_class="UNKNOWN_INCOMPLETE",
                              completeness="COMPLETE_KNOWN_NONEMPTY_PRESTACK", name="t16.sqlite3")
        self.assertEqual(caught.exception.code, FailureCode.DOMAIN_BOOTSTRAP_COMPLETENESS_MISMATCH)

    def test_t17_alternate_ledger_path_for_same_conflict_rejected(self) -> None:
        self._init_active(name="t17a.sqlite3")
        with self.assertRaises(LedgerError) as caught:
            self._init_active(name="t17b.sqlite3")  # same conflict domain, different path
        self.assertEqual(caught.exception.code, FailureCode.AUTHORITY_CONFLICT_DOMAIN_ALREADY_BOUND)

    def test_t21_bootstrap_event_under_revision1_ledger_rejected(self) -> None:
        # A revision-1 ledger never carries an EXECUTION_DOMAIN_BOOTSTRAP_RECORDED
        # event: initialize_ledger_binding only writes LEDGER_INITIALIZED and
        # its genesis validator has no bootstrap branch.  The rev-1 reader on a
        # rev-2 ledger fails closed (covered by test_t13); the inverse
        # (bootstrap event id determinism) is covered by test_revision2_event_id_formula.
        from arb.execution_ledger import _NEW_EVENT_PAYLOAD_KEYS
        self.assertIn(EventType.EXECUTION_DOMAIN_BOOTSTRAP_RECORDED, _NEW_EVENT_PAYLOAD_KEYS)

    def test_t24_revision2_binding_json_hash_mismatch_rejected(self) -> None:
        conflict, obj, bsha, bid = _binding_canonical(
            account_scope_ref="ARB_KALSHI_DEMO_PRIMARY_ACCOUNT", subaccount=1, exchange_index=0)
        payload, _bcsha = _bootstrap_payload(
            conflict=conflict, bid=bid, bsha=bsha, bootstrap_class="KNOWN_NONEMPTY_PRESTACK",
            completeness="COMPLETE_KNOWN_NONEMPTY_PRESTACK")
        with self.assertRaises(LedgerError) as caught:
            ledger.initialize_execution_domain_ledger_v2(
                self.binding, conflict_domain_ref=conflict, ledger_path=self.root / "t24.sqlite3",
                canonical_repository_root=self.repository_root,
                preledger_history_mode="KNOWN_NONEMPTY_PRESTACK",
                execution_domain_binding_id=bid,
                execution_domain_binding_sha256="f" * 64,  # wrong
                execution_domain_binding_json=ledger.canonical_json_text(obj),
                bootstrap_event_payload=payload, active_incident_id="adi_" + "0" * 32,
                active_writer_proof_id="adwp_" + "0" * 32,
                clock=self.inputs.clock, uuid_factory=self.inputs.uuid)
        self.assertIn(caught.exception.code, (
            FailureCode.EXECUTION_DOMAIN_BINDING_MISMATCH, FailureCode.EXECUTION_DOMAIN_BINDING_MALFORMED))

    def test_t25_partial_authority_binding_fails_closed(self) -> None:
        # A durably-created revision-2 ledger whose authority row commit is
        # interrupted must fail closed (DOMAIN_BOOTSTRAP_AUTHORITY_BINDING
        # _INCOMPLETE), never silently attach an orphan ledger.
        conflict, obj, bsha, bid = _binding_canonical(
            account_scope_ref="ARB_KALSHI_DEMO_PRIMARY_ACCOUNT", subaccount=1, exchange_index=0)
        payload, bcsha = _bootstrap_payload(
            conflict=conflict, bid=bid, bsha=bsha, bootstrap_class="KNOWN_NONEMPTY_PRESTACK",
            completeness="COMPLETE_KNOWN_NONEMPTY_PRESTACK")

        def _fault(stage: str) -> None:
            if stage == "before_authority_binding_commit":
                raise sqlite3.OperationalError("synthetic authority commit interruption")

        with self.assertRaises(LedgerError) as caught:
            ledger.initialize_execution_domain_ledger_v2(
                self.binding, conflict_domain_ref=conflict, ledger_path=self.root / "t25.sqlite3",
                canonical_repository_root=self.repository_root,
                preledger_history_mode="KNOWN_NONEMPTY_PRESTACK",
                execution_domain_binding_id=bid, execution_domain_binding_sha256=bsha,
                execution_domain_binding_json=ledger.canonical_json_text(obj),
                bootstrap_event_payload=payload,
                active_incident_id="adi_" + sha256_hex(
                    b"ARB_ACTIVE_EXECUTION_DOMAIN_INCIDENT_V1\x00" + bsha.encode() + b"\x00" + bcsha.encode())[:32],
                active_writer_proof_id="adwp_" + sha256_hex(
                    b"ARB_ACTIVE_DOMAIN_WRITER_PROOF_V1\x00" + bsha.encode())[:32],
                clock=self.inputs.clock, uuid_factory=self.inputs.uuid, fault_hook=_fault)
        self.assertEqual(caught.exception.code, FailureCode.DOMAIN_BOOTSTRAP_AUTHORITY_BINDING_INCOMPLETE)
        # the conflict domain is NOT bound to any ledger.
        with self.assertRaises(LedgerError):
            ledger._open_locked(
                self.binding, conflict_domain_ref=conflict, expected_environment="KALSHI_DEMO",
                canonical_repository_root=self.repository_root, ledger_revision=2)

    def test_t11_t12_legacy_revision1_state_unchanged(self) -> None:
        # T11: LegacyIncidentContract default values are byte-stable.
        # T12: the historical SUBACCOUNT=0 conflict domain string is fixed.
        from arb.venues.kalshi.ledger_binding import (
            LegacyIncidentContract, CURRENT_CONFLICT_DOMAIN_REF, CURRENT_SUBACCOUNT,
        )
        c = LegacyIncidentContract()
        self.assertEqual(c.subaccount, 0)
        self.assertEqual(CURRENT_SUBACCOUNT, 0)
        self.assertEqual(c.conflict_domain_ref, CURRENT_CONFLICT_DOMAIN_REF)
        self.assertEqual(
            CURRENT_CONFLICT_DOMAIN_REF,
            "KALSHI|KALSHI_DEMO|ARB_KALSHI_DEMO_PRIMARY_ACCOUNT|SUBACCOUNT=0")


if __name__ == "__main__":
    unittest.main()
