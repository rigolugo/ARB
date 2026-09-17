"""Offline tests for the R1-D07 N1 fresh read-only state revalidation V2
successor launcher, CORRECTION_04
(`project_archive/r1_d07_2026_09_14/n1_fresh_read_only_state_revalidation_v2/
RUN_R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_02.ps1`).

CORRECTION_04 (C04-T01..C04-T09) corrects a validator implementation defect
accepted after a halted empirical run: `check_frozen_production_identity()`
now compares only the two frozen `authority_path`/`ledger_path` metadata
strings with Windows drive-letter/component case-insensitive lexical
`casefold()` equality, while every other of the 17 frozen identity fields,
and the wholly independent actual-source-binding gate
(`check_production_source_binding`), remain exact and unchanged.

CORRECTION_03 adds direct proofs that the result artifact is created
atomically and exclusively (C03-T01..C03-T07): a real NTFS hard link outside
every protected root that aliases a synthetic authority or ledger store, an
ordinary pre-existing output file, and a deterministic validation-to-create
race are all refused with zero modification of the existing object, while a
genuinely new safe destination still receives the result. Every CORRECTION_01
and CORRECTION_02 test below is preserved.

Three complementary proof strategies are used:

1. Pure-function unit tests (`TestEmbeddedPureLogic`): the exact embedded
   Python source is extracted verbatim from the delivered `.ps1` file (the
   same bytes the launcher itself materializes to a temp file at runtime)
   and executed in a fresh module namespace, giving direct access to
   `production_expectations`, `check_production_source_binding`,
   `classify_output_sink`, `validate_mandatory_observations`,
   `check_frozen_production_identity`, `check_candidate02_contract_values`,
   and `check_unresolved_gate` -- the exact gate logic the launcher runs,
   not a reimplementation of it.

2. Static surface tests (`TestProductionParameterSurface`): proofs that the
   production CLI surface exposes no parameter capable of substituting a
   frozen source, identity, expected fill ID, or expected Candidate-02
   identity. These are structural theorems about what the launcher *cannot*
   be asked to do, which no positive-path test can establish.

3. Real end-to-end launcher tests (`TestV2LauncherEndToEnd`): a synthetic
   active-execution-domain N1 fixture (authority store + revision-2 ledger)
   is built with the same canonical construction helpers the accepted
   `tests/test_kalshi_ledger_binding.py` suite already uses, and the actual
   delivered `.ps1` is invoked via `powershell.exe` against it.

   Every end-to-end invocation in this module runs in the launcher's
   explicitly nonproduction fixture mode
   (`IDENTITY_BINDING_AND_TEST_SEAM.md` Design B), which is structurally
   incapable of emitting the production terminal PASS marker: the probe
   reserves exit code 0 and status `READ_ONLY_REVALIDATION_PASS` for a
   production observation, a fixture observation returns exit 3 /
   `NONPRODUCTION_FIXTURE_COMPLETE`, and the launcher prints
   `READ_ONLY_REVALIDATION_TERMINAL=PASS` only for exit 0.

   `run_launcher` refuses to build a production-mode command line, so no
   test in this module can invoke the reader against the frozen deployed
   topology.

No test in this module touches deployed N1 state
(`C:\\b1\\kals\\arb_state\\...`) and none performs Kalshi/network access:
every SQLite file used here is created fresh under a per-test temporary
directory and discarded at teardown. The one test that proves the deployed
state root is refused as an output sink relies on the guard's purely
lexical first layer, which performs zero filesystem access on that root.

CORRECTION_01 -> CORRECTION_02 test mapping (C02-T13): every CORRECTION_01
theorem T01-T22 is preserved or superseded by a strictly stronger
equivalent; see `CORRECTION_02_TEST_MAPPING.txt` in the review package and
the `correction_01_theorem` docstring annotations below.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import arb.execution_ledger as el
from arb.execution_ledger import AuthorityNamespaceBinding, canonical_json_bytes, initialize_authority_namespace
from arb.venues.kalshi import ledger_binding as lb
from arb.venues.kalshi.minimal_market_maker_experiment_runner import _load_sha_bound_risk_config

LAUNCHER_PATH = (
    REPO_ROOT / "project_archive" / "r1_d07_2026_09_14"
    / "n1_fresh_read_only_state_revalidation_v2"
    / "RUN_R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_02.ps1"
)
ACCOUNT = "ARB_KALSHI_DEMO_PRIMARY_ACCOUNT"
EXPECTED_FILL_ID = "07212270-bae1-9bda-8e24-cd2221a09d60"
PWSH = shutil.which("powershell.exe") or shutil.which("pwsh.exe") or shutil.which("pwsh")

# Exact frozen accepted N1 identity per
# 03_REVIEW_DECISION/MARCO_BLOCK_CORRECTION_01_HANDOFF.md, reproduced here
# ONLY as an independent expected value (proving the launcher's own embedded
# constant equals this, not the other way around).
EXPECTED_FROZEN_PRODUCTION_IDENTITY = {
    "authority_namespace_id": "ARB_KALSHI_DEMO_PRIMARY_AUTHORITY_V1",
    "authority_instance_id": "772b53a9-7915-4133-957b-3d6c24dfdfc7",
    "authority_schema_revision": 1,
    "authority_path": "C:\\b1\\kals\\arb_state\\kalshi_demo_primary_v1\\authority\\arb_execution_authority_v1.sqlite3",
    "authority_store_path_identity_sha256": "dbf0afa85aa59c82879cc78e24340d7035074b43879df39eca98a1e3ac83f899",
    "ledger_instance_id": "485b37e9-738d-49f8-99cf-5f2e69589de6",
    "ledger_schema_revision": 2,
    "ledger_path": "C:\\b1\\kals\\arb_state\\kalshi_demo_primary_v1\\ledger\\subaccount1_execution_v2.sqlite3",
    "ledger_path_identity_sha256": "ab36fd934f013f16795f161f20f1d63daecf8a385bfe260fc3a7bb8945e4d3b3",
    "conflict_domain_ref": "KALSHI|KALSHI_DEMO|ARB_KALSHI_DEMO_PRIMARY_ACCOUNT|SUBACCOUNT=1",
    "execution_domain_binding_id": "KEDB1_f6aa344c8b573f2d436f76e5dc58601f8583af71a2555922d35f250ded123a02",
    "execution_domain_binding_sha256": "f6aa344c8b573f2d436f76e5dc58601f8583af71a2555922d35f250ded123a02",
    "bootstrap_contract_sha256": "c387e47c2862e6082e75bc8eb8dfa47ed085ec7be98e8426970a278a953e7360",
    "active_contract_id": "AEDC1_f2d62188997b28d2d36f4686c271cb9be43f10d1cbdf217960dda0ecf8e61c53",
    "active_contract_sha256": "f2d62188997b28d2d36f4686c271cb9be43f10d1cbdf217960dda0ecf8e61c53",
    "incident_id": "adi_2c5c16c8e7299d0e6fccb23caec7c4d4",
    "writer_proof_id": "adwp_0b247ef6546e88308017a3168b9ad2b8",
}

# Frozen production filesystem topology per
# 04_IMPLEMENTATION_GUIDANCE/ACTUAL_SOURCE_PATH_BINDING.md, reproduced here
# only as an independent expected value. No test opens any of these paths.
EXPECTED_FROZEN_SOURCES = {
    "repo": "C:\\b1\\kals\\ARB",
    "authority": "C:\\b1\\kals\\arb_state\\kalshi_demo_primary_v1\\authority\\arb_execution_authority_v1.sqlite3",
    "ledger": "C:\\b1\\kals\\arb_state\\kalshi_demo_primary_v1\\ledger\\subaccount1_execution_v2.sqlite3",
}
EXPECTED_FROZEN_DEPLOYMENT_ROOT = "C:\\b1\\kals\\arb_state"

# The five observations MARCO_BLOCK_CORRECTION_02_HANDOFF.md defect 4 names
# explicitly, plus the new actual-source-path observations that same defect
# requires be added to the mandatory validator.
C02_T09_REQUIRED_MANDATORY_PATHS = (
    "observation_timestamp_utc",
    "identity.authority_schema_revision",
    "domain.bootstrap_contract_sha256",
    "identity.ledger_path",
    "source_binding.resolved_repo_path",
    "source_binding.resolved_authority_source_path",
    "source_binding.resolved_ledger_source_path",
)


def _extract_embedded_probe_source() -> str:
    """Extract the exact Python source the launcher itself materializes to a
    temp file at invocation time, from between the `$Py = @'` ... `'@`
    here-string markers in the delivered `.ps1`. This is the same bytes, not
    a separately maintained copy."""
    text = LAUNCHER_PATH.read_text(encoding="utf-8")
    match = re.search(r"\$Py = @'\r?\n(.*?)\r?\n'@", text, re.DOTALL)
    if match is None:
        raise AssertionError("could not locate embedded $Py = @'...'@ here-string in the launcher source")
    return match.group(1)


def _load_embedded_probe_module() -> dict:
    """Execute the extracted embedded source in a fresh namespace (with
    __name__ deliberately not '__main__', so the `if __name__ ==
    \"__main__\":` guard at the bottom does not fire) and return that
    namespace as a lightweight module-like object."""
    source = _extract_embedded_probe_source()
    namespace: dict = {"__name__": "embedded_r1d07_n1_v2_probe"}
    exec(compile(source, "<embedded_probe>", "exec"), namespace)
    return namespace


def _ps1_param_block() -> str:
    text = LAUNCHER_PATH.read_text(encoding="utf-8")
    match = re.search(r"^param\((.*?)^\)", text, re.DOTALL | re.MULTILINE)
    if match is None:
        raise AssertionError("could not locate the launcher param() block")
    return match.group(1)


def _ps1_declared_parameters() -> set:
    """Every `-Name` the launcher's param() block declares, lowercased."""
    # Every parameter is declared with an explicit type annotation
    # (`[string]$X`, `[switch]$X`, `[string[]]$X`, `[Parameter(...)][string]$X`),
    # so anchoring on the closing bracket matches declarations only -- never an
    # ordinary `$variable` appearing inside an attribute argument.
    return {name.lower() for name in re.findall(r"\]\$([A-Za-z][A-Za-z0-9]*)", _ps1_param_block())}


def _probe_declared_arguments() -> set:
    """Every `--flag` the embedded probe's argparse surface declares."""
    return set(re.findall(r'parser\.add_argument\("(--[a-z0-9-]+)"', _extract_embedded_probe_source()))


class TestEmbeddedPureLogic(unittest.TestCase):
    """Pure-function proofs against the exact embedded probe logic,
    requiring no SQLite fixture and no launcher subprocess."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.probe = _load_embedded_probe_module()

    # -- preserved CORRECTION_01 T01-T08 (frozen internal identity gate) ----

    def test_c01_t01_frozen_constants_equal_accepted_n1_identities(self) -> None:
        """correction_01_theorem: T01 (preserved unchanged)."""
        self.assertEqual(self.probe["FROZEN_PRODUCTION_IDENTITY"], EXPECTED_FROZEN_PRODUCTION_IDENTITY)

    def test_c01_full_identity_match_produces_zero_mismatch_failures(self) -> None:
        check = self.probe["check_frozen_production_identity"]
        self.assertEqual(check(dict(EXPECTED_FROZEN_PRODUCTION_IDENTITY)), [])

    def test_c01_none_observed_identity_fields_are_skipped_not_flagged(self) -> None:
        # A field this tool could not observe at all is already recorded by
        # validate_mandatory_observations as MISSING_REQUIRED_FIELD; the
        # identity gate must not also emit a confusing duplicate
        # PRODUCTION_IDENTITY_MISMATCH for the same gap.
        check = self.probe["check_frozen_production_identity"]
        observed = dict(EXPECTED_FROZEN_PRODUCTION_IDENTITY)
        observed["authority_namespace_id"] = None
        self.assertEqual(check(observed), [])
        # ...but it IS still reported as a missing mandatory observation.
        self.assertIn(
            "MISSING_REQUIRED_FIELD:identity.authority_namespace_id",
            self.probe["validate_mandatory_observations"]({"identity": {"authority_namespace_id": None}}),
        )

    def test_c01_t02_to_t08_every_frozen_identity_field_fails_closed(self) -> None:
        """correction_01_theorem: T02-T08 (preserved, widened from the
        original seven named fields to all 17)."""
        check = self.probe["check_frozen_production_identity"]
        for field, expected in EXPECTED_FROZEN_PRODUCTION_IDENTITY.items():
            with self.subTest(field=field):
                observed = dict(EXPECTED_FROZEN_PRODUCTION_IDENTITY)
                observed[field] = 99 if isinstance(expected, int) else "WRONG"
                self.assertEqual(check(observed), [f"PRODUCTION_IDENTITY_MISMATCH:{field}"])

    # -- CORRECTION_04 (authority_path / ledger_path Windows drive-letter /
    # -- component case-only lexical casefold equality; every other frozen
    # -- identity field remains exact) -------------------------------------

    def test_c04_t01_authority_path_drive_letter_case_change_produces_zero_mismatch(self) -> None:
        """correction_04_theorem: T01."""
        check = self.probe["check_frozen_production_identity"]
        observed = dict(EXPECTED_FROZEN_PRODUCTION_IDENTITY)
        observed["authority_path"] = observed["authority_path"].replace("C:\\", "c:\\", 1)
        self.assertEqual(check(observed), [])

    def test_c04_t02_ledger_path_drive_letter_case_change_produces_zero_mismatch(self) -> None:
        """correction_04_theorem: T02."""
        check = self.probe["check_frozen_production_identity"]
        observed = dict(EXPECTED_FROZEN_PRODUCTION_IDENTITY)
        observed["ledger_path"] = observed["ledger_path"].replace("C:\\", "c:\\", 1)
        self.assertEqual(check(observed), [])

    def test_c04_t03_arbitrary_component_case_only_variation_produces_zero_mismatch(self) -> None:
        """correction_04_theorem: T03."""
        check = self.probe["check_frozen_production_identity"]
        observed = dict(EXPECTED_FROZEN_PRODUCTION_IDENTITY)
        observed["authority_path"] = observed["authority_path"].replace("arb_state", "ARB_STATE")
        observed["ledger_path"] = observed["ledger_path"].upper()
        self.assertEqual(check(observed), [])

    def test_c04_t04_materially_different_authority_path_still_fails_closed(self) -> None:
        """correction_04_theorem: T04."""
        check = self.probe["check_frozen_production_identity"]
        observed = dict(EXPECTED_FROZEN_PRODUCTION_IDENTITY)
        observed["authority_path"] = (
            "C:\\b1\\kals\\arb_state\\kalshi_demo_primary_v1\\authority\\other_store.sqlite3"
        )
        self.assertEqual(check(observed), ["PRODUCTION_IDENTITY_MISMATCH:authority_path"])

    def test_c04_t05_materially_different_ledger_path_still_fails_closed(self) -> None:
        """correction_04_theorem: T05."""
        check = self.probe["check_frozen_production_identity"]
        observed = dict(EXPECTED_FROZEN_PRODUCTION_IDENTITY)
        observed["ledger_path"] = (
            "C:\\b1\\kals\\arb_state\\kalshi_demo_primary_v1\\ledger\\other_ledger.sqlite3"
        )
        self.assertEqual(check(observed), ["PRODUCTION_IDENTITY_MISMATCH:ledger_path"])

    def test_c04_t06_no_normalization_broadening(self) -> None:
        """correction_04_theorem: T06 -- the casefold-only rule must not
        accept forward-slash substitution, an inserted dot-segment, a
        different drive, UNC spelling, or a prefix/suffix alteration."""
        check = self.probe["check_frozen_production_identity"]
        base = EXPECTED_FROZEN_PRODUCTION_IDENTITY["authority_path"]
        variants = {
            "forward_slash": base.replace("\\", "/"),
            "dot_segment": base.replace("\\kals\\", "\\kals\\.\\"),
            "different_drive": "D:" + base[2:],
            "unc": "\\\\localhost\\" + base[0] + "$" + base[2:],
            "prefix": "X" + base,
            "suffix": base + "X",
        }
        for label, variant_value in variants.items():
            with self.subTest(variant=label):
                observed = dict(EXPECTED_FROZEN_PRODUCTION_IDENTITY)
                observed["authority_path"] = variant_value
                self.assertEqual(check(observed), ["PRODUCTION_IDENTITY_MISMATCH:authority_path"])

    def test_c04_t07_non_path_identities_remain_case_sensitive(self) -> None:
        """correction_04_theorem: T07 -- the casefold relaxation applies only
        to `authority_path`/`ledger_path`; every other identity key must
        still fail closed on a case-only mutation."""
        check = self.probe["check_frozen_production_identity"]
        for field in ("authority_namespace_id", "execution_domain_binding_id", "incident_id"):
            with self.subTest(field=field):
                observed = dict(EXPECTED_FROZEN_PRODUCTION_IDENTITY)
                observed[field] = observed[field].swapcase()
                self.assertEqual(check(observed), [f"PRODUCTION_IDENTITY_MISMATCH:{field}"])

    def test_c04_t08_case_equivalent_identity_metadata_does_not_relax_source_binding(self) -> None:
        """correction_04_theorem: T08 -- the independent stale-copy
        source-binding gate must still refuse a byte-identical copy at the
        wrong actual location even when the embedded authority_path/
        ledger_path metadata strings are only Windows-drive-letter-case
        different from (and therefore now accepted by) the frozen metadata
        identity gate."""
        identity_check = self.probe["check_frozen_production_identity"]
        observed_identity = dict(EXPECTED_FROZEN_PRODUCTION_IDENTITY)
        observed_identity["authority_path"] = observed_identity["authority_path"].replace("C:\\", "c:\\", 1)
        observed_identity["ledger_path"] = observed_identity["ledger_path"].replace("C:\\", "c:\\", 1)
        self.assertEqual(identity_check(observed_identity), [])

        source_check = self.probe["check_production_source_binding"]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            accepted = root / "accepted_deployment"
            copies = root / "stale_copies"
            accepted.mkdir()
            copies.mkdir()
            repo = root / "repo"
            repo.mkdir()
            content = {"authority": b"accepted authority store bytes", "ledger": b"accepted ledger store bytes"}
            for name, data in content.items():
                (accepted / f"{name}.sqlite3").write_bytes(data)
                (copies / f"{name}.sqlite3").write_bytes(data)
            failures = source_check(
                resolved_repo=str(repo),
                resolved_authority=str(copies / "authority.sqlite3"),
                resolved_ledger=str(copies / "ledger.sqlite3"),
                expected_repo=str(repo),
                expected_authority=str(accepted / "authority.sqlite3"),
                expected_ledger=str(accepted / "ledger.sqlite3"),
            )
            self.assertEqual(
                failures,
                ["PRODUCTION_SOURCE_PATH_MISMATCH:authority", "PRODUCTION_SOURCE_PATH_MISMATCH:ledger"],
            )

    def test_c04_t09_path_case_only_variant_does_not_block_completeness(self) -> None:
        """correction_04_theorem: T09 -- a path case-only variant alone must
        not itself create any failure key; a materially different path must
        still prevent it."""
        check = self.probe["check_frozen_production_identity"]
        observed_case_only = dict(EXPECTED_FROZEN_PRODUCTION_IDENTITY)
        observed_case_only["authority_path"] = observed_case_only["authority_path"].replace("C:\\", "c:\\", 1)
        observed_case_only["ledger_path"] = observed_case_only["ledger_path"].replace("C:\\", "c:\\", 1)
        self.assertEqual(check(observed_case_only), [])
        observed_material = dict(EXPECTED_FROZEN_PRODUCTION_IDENTITY)
        observed_material["authority_path"] = "C:\\different\\authority.sqlite3"
        self.assertEqual(check(observed_material), ["PRODUCTION_IDENTITY_MISMATCH:authority_path"])

    # -- preserved CORRECTION_01 T11-T13 (unresolved/conflict gates) -------

    def test_c01_t11_unresolved_write_present_fails_closed(self) -> None:
        """correction_01_theorem: T11 (preserved unchanged)."""
        check = self.probe["check_unresolved_gate"]
        self.assertEqual(
            check(unresolved_write_ids=("req-1",), unresolved_cancel_ids=(), fill_conflicts=()),
            ["UNRESOLVED_WRITE_PRESENT"],
        )
        self.assertEqual(check(unresolved_write_ids=(), unresolved_cancel_ids=(), fill_conflicts=()), [])

    def test_c01_t12_unresolved_cancel_present_fails_closed(self) -> None:
        """correction_01_theorem: T12 (preserved unchanged)."""
        check = self.probe["check_unresolved_gate"]
        self.assertEqual(
            check(unresolved_write_ids=(), unresolved_cancel_ids=("attempt-1",), fill_conflicts=()),
            ["UNRESOLVED_CANCEL_PRESENT"],
        )

    def test_c01_t13_fill_conflict_present_fails_closed(self) -> None:
        """correction_01_theorem: T13 (preserved unchanged)."""
        check = self.probe["check_unresolved_gate"]
        self.assertEqual(
            check(unresolved_write_ids=(), unresolved_cancel_ids=(), fill_conflicts=("fill-1",)),
            ["FILL_CONFLICT_PRESENT"],
        )

    # -- C02-T01: frozen production sources -------------------------------

    def test_c02_t01_production_expectations_are_the_frozen_contract_values(self) -> None:
        expectations = self.probe["production_expectations"]()
        self.assertEqual(expectations["repo"], EXPECTED_FROZEN_SOURCES["repo"])
        self.assertEqual(expectations["authority"], EXPECTED_FROZEN_SOURCES["authority"])
        self.assertEqual(expectations["ledger"], EXPECTED_FROZEN_SOURCES["ledger"])
        self.assertEqual(
            expectations["conflict_domain"],
            "KALSHI|KALSHI_DEMO|ARB_KALSHI_DEMO_PRIMARY_ACCOUNT|SUBACCOUNT=1",
        )
        self.assertEqual(expectations["identity"], EXPECTED_FROZEN_PRODUCTION_IDENTITY)
        self.assertEqual(self.probe["FROZEN_DEPLOYMENT_ROOT"], EXPECTED_FROZEN_DEPLOYMENT_ROOT)
        # Takes no arguments at all: there is no runtime value that can reach it.
        import inspect
        self.assertEqual(list(inspect.signature(self.probe["production_expectations"]).parameters), [])

    def test_c02_t01_source_binding_gate_positive_and_negative(self) -> None:
        check = self.probe["check_production_source_binding"]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo, authority, ledger = root / "repo", root / "a.sqlite3", root / "l.sqlite3"
            repo.mkdir()
            authority.write_bytes(b"a")
            ledger.write_bytes(b"l")
            self.assertEqual(
                check(resolved_repo=str(repo), resolved_authority=str(authority), resolved_ledger=str(ledger),
                      expected_repo=str(repo), expected_authority=str(authority), expected_ledger=str(ledger)),
                [],
            )
            # Windows comparison must be case-insensitive after normalization.
            self.assertEqual(
                check(resolved_repo=str(repo).upper(), resolved_authority=str(authority).upper(),
                      resolved_ledger=str(ledger).upper(), expected_repo=str(repo),
                      expected_authority=str(authority), expected_ledger=str(ledger)),
                [] if os.name == "nt" else
                ["PRODUCTION_SOURCE_PATH_MISMATCH:repo", "PRODUCTION_SOURCE_PATH_MISMATCH:authority",
                 "PRODUCTION_SOURCE_PATH_MISMATCH:ledger"],
            )
            for label, kwargs in (
                ("repo", {"resolved_repo": str(root / "other_repo")}),
                ("authority", {"resolved_authority": str(root / "other_a.sqlite3")}),
                ("ledger", {"resolved_ledger": str(root / "other_l.sqlite3")}),
            ):
                with self.subTest(label=label):
                    call = dict(
                        resolved_repo=str(repo), resolved_authority=str(authority), resolved_ledger=str(ledger),
                        expected_repo=str(repo), expected_authority=str(authority), expected_ledger=str(ledger),
                    )
                    call.update(kwargs)
                    self.assertEqual(check(**call), [f"PRODUCTION_SOURCE_PATH_MISMATCH:{label}"])
            # A source that could not be resolved at all is a missing
            # mandatory observation, not a silent pass.
            self.assertIn(
                "MISSING_REQUIRED_FIELD:source_binding.resolved_authority_source_path",
                check(resolved_repo=str(repo), resolved_authority=None, resolved_ledger=str(ledger),
                      expected_repo=str(repo), expected_authority=str(authority), expected_ledger=str(ledger)),
            )

    # -- C02-T02: internally valid copies at alternate paths --------------

    def test_c02_t02_internally_valid_copy_at_alternate_path_fails_source_binding(self) -> None:
        """A byte-identical copy of the accepted stores keeps every identity
        embedded in its own metadata, so the metadata gate alone would accept
        it (Marco BLOCK defect 1). The source-binding gate is what refuses
        it.

        CORRECTION_03 note: the CORRECTION_02 version of this test passed the
        frozen production paths as the EXPECTED side. The gate link-resolves
        both sides, and on Windows `Path.resolve()` opens a zero-access handle
        to an existing path -- so that test opened a handle on the deployed
        authority/ledger stores. It now uses a synthetic "accepted" location;
        the frozen production values themselves are proven separately, purely
        lexically, by `test_c02_t01_production_expectations_are_the_frozen_contract_values`."""
        check = self.probe["check_production_source_binding"]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            accepted = root / "accepted_deployment"
            copies = root / "stale_copies"
            accepted.mkdir()
            copies.mkdir()
            repo = root / "repo"
            repo.mkdir()
            content = {"authority": b"accepted authority store bytes", "ledger": b"accepted ledger store bytes"}
            for name, data in content.items():
                (accepted / f"{name}.sqlite3").write_bytes(data)
                (copies / f"{name}.sqlite3").write_bytes(data)
            failures = check(
                resolved_repo=str(repo),
                resolved_authority=str(copies / "authority.sqlite3"),
                resolved_ledger=str(copies / "ledger.sqlite3"),
                expected_repo=str(repo),
                expected_authority=str(accepted / "authority.sqlite3"),
                expected_ledger=str(accepted / "ledger.sqlite3"),
            )
            self.assertEqual(
                failures,
                ["PRODUCTION_SOURCE_PATH_MISMATCH:authority", "PRODUCTION_SOURCE_PATH_MISMATCH:ledger"],
            )
            # The copies really are byte-identical to the accepted files.
            for name, data in content.items():
                self.assertEqual((copies / f"{name}.sqlite3").read_bytes(), (accepted / f"{name}.sqlite3").read_bytes())
        # The metadata identity gate, on its own, would have been satisfied:
        # this is exactly why both layers are required.
        self.assertEqual(
            self.probe["check_frozen_production_identity"](dict(EXPECTED_FROZEN_PRODUCTION_IDENTITY)), [],
        )

    # -- C02-T03 to C02-T06: output sink safety ---------------------------

    def test_c02_t04_t05_protected_root_rejected_and_nothing_created(self) -> None:
        """Containment rejection, proven against a simulated protected root
        so the 'creates nothing' half of the theorem can be asserted on a
        real directory, and separately against the real frozen roots (whose
        rejection happens in the guard's zero-filesystem-access lexical
        layer)."""
        classify = self.probe["classify_output_sink"]
        with tempfile.TemporaryDirectory() as tmp:
            protected = Path(tmp) / "protected_root"
            (protected / "nested").mkdir(parents=True)
            for label, requested in (
                ("direct_child", protected / "out.json"),
                ("nested_child", protected / "nested" / "out.json"),
                ("normalized_traversal", protected / "nested" / ".." / "out.json"),
                ("root_itself", protected),
            ):
                with self.subTest(label=label):
                    resolved, failure = classify(str(requested), protected_roots=[str(protected)], protected_files=[])
                    self.assertIsNone(resolved)
                    self.assertTrue(failure.startswith("UNSAFE_OUTPUT_SINK:PROTECTED_ROOT"), failure)
            # Nothing at all was created under the protected root.
            self.assertEqual(sorted(p.name for p in protected.rglob("*")), ["nested"])
            # A sibling whose name merely starts with the root's name is not
            # treated as contained.
            sibling = Path(tmp) / "protected_root_sibling" / "out.json"
            sibling.parent.mkdir()
            resolved, failure = classify(str(sibling), protected_roots=[str(protected)], protected_files=[])
            self.assertIsNone(failure, failure)
            self.assertIsNotNone(resolved)

    @unittest.skipUnless(os.name == "nt", "the frozen production roots are Windows paths")
    def test_c02_t05_frozen_deployment_root_and_repo_root_are_rejected(self) -> None:
        classify = self.probe["classify_output_sink"]
        expectations = self.probe["production_expectations"]()
        roots = [expectations["repo"], self.probe["FROZEN_DEPLOYMENT_ROOT"]]
        for requested in (
            self.probe["FROZEN_DEPLOYMENT_ROOT"] + "\\kalshi_demo_primary_v1\\result.json",
            self.probe["FROZEN_DEPLOYMENT_ROOT"] + "\\nested\\..\\result.json",
            expectations["repo"] + "\\project_archive\\result.json",
            expectations["repo"] + "\\result.json",
        ):
            with self.subTest(requested=requested):
                resolved, failure = classify(requested, protected_roots=roots, protected_files=[])
                self.assertIsNone(resolved)
                self.assertTrue(failure.startswith("UNSAFE_OUTPUT_SINK:PROTECTED_ROOT"), failure)

    def test_c02_t06_protected_file_alias_rejected_without_modifying_it(self) -> None:
        classify = self.probe["classify_output_sink"]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            protected_files = []
            for name, content in (("authority.sqlite3", b"AUTH"), ("ledger.sqlite3", b"LEDG"),
                                  ("candidate02.json", b"{}"), ("launcher.ps1", b"param()")):
                target = root / name
                target.write_bytes(content)
                protected_files.append(target)
            for target in protected_files:
                with self.subTest(target=target.name):
                    before = target.read_bytes()
                    resolved, failure = classify(
                        str(target), protected_roots=[], protected_files=[str(p) for p in protected_files],
                    )
                    self.assertIsNone(resolved)
                    self.assertTrue(failure.startswith("UNSAFE_OUTPUT_SINK:PROTECTED_FILE_ALIAS"), failure)
                    self.assertEqual(target.read_bytes(), before)
            # A distinct sibling file is safe.
            safe = root / "safe_result.json"
            resolved, failure = classify(
                str(safe), protected_roots=[], protected_files=[str(p) for p in protected_files],
            )
            self.assertIsNone(failure, failure)
            self.assertEqual(resolved, str(safe.resolve()))

    def test_c02_t06_symlink_or_junction_parent_into_protected_root_rejected(self) -> None:
        """OUTPUT_SINK_SAFETY.md requires that a destination which resolves
        through a junction/symlink parent INTO a protected root is rejected.
        Creating a link may require privileges the local session does not
        have; the test skips rather than weakening the assertion."""
        classify = self.probe["classify_output_sink"]
        with tempfile.TemporaryDirectory() as tmp:
            # The guard's documented precondition is that protected roots are
            # supplied in canonical resolved form -- which the frozen
            # production constants are, but which a Windows temp directory
            # (returned in 8.3 short form) is not, so resolve it here.
            root = Path(tmp).resolve()
            protected = root / "protected_root"
            protected.mkdir()
            link = root / "innocent_link"
            # A Windows directory junction needs no special privilege, unlike
            # a symbolic link; prefer it, fall back to a symlink, and skip
            # rather than weaken the assertion if neither is available.
            junction = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link), str(protected)],
                capture_output=True, text=True,
            ) if os.name == "nt" else None
            if junction is None or junction.returncode != 0 or not link.exists():
                try:
                    link.symlink_to(protected, target_is_directory=True)
                except (OSError, NotImplementedError) as exc:
                    self.skipTest(f"directory links unavailable in this session: {type(exc).__name__}: {exc}")
            requested = link / "out.json"
            # The lexical layer cannot see through the link...
            self.assertFalse(
                self.probe["is_within_root"](
                    self.probe["normalize_for_compare"](str(requested)),
                    self.probe["normalize_for_compare"](str(protected)),
                )
            )
            # ...but the resolving layer does, and rejects it.
            resolved, failure = classify(str(requested), protected_roots=[str(protected)], protected_files=[])
            self.assertIsNone(resolved)
            self.assertTrue(failure.startswith("UNSAFE_OUTPUT_SINK:PROTECTED_ROOT_VIA_LINK"), failure)
            self.assertEqual(list(protected.iterdir()), [])

    def test_c02_t03_unresolvable_or_empty_sink_fails_closed(self) -> None:
        classify = self.probe["classify_output_sink"]
        resolved, failure = classify(None, protected_roots=[], protected_files=[])
        self.assertIsNone(resolved)
        self.assertEqual(failure, "MISSING_REQUIRED_FIELD:output_sink.requested_output_path")
        resolved, failure = classify("", protected_roots=[], protected_files=[])
        self.assertIsNone(resolved)
        self.assertEqual(failure, "MISSING_REQUIRED_FIELD:output_sink.requested_output_path")

    # -- C02-T09: mandatory observation validator -------------------------

    def test_c02_t09_validator_declares_every_required_mandatory_path(self) -> None:
        declared = set(self.probe["MANDATORY_NON_NULL_OBSERVATIONS"])
        for dotted in C02_T09_REQUIRED_MANDATORY_PATHS:
            with self.subTest(dotted=dotted):
                self.assertIn(dotted, declared)

    def test_c02_t09_empty_result_reports_every_mandatory_path_missing(self) -> None:
        validate = self.probe["validate_mandatory_observations"]
        failures = set(validate({}))
        for dotted in self.probe["MANDATORY_NON_NULL_OBSERVATIONS"]:
            self.assertIn(f"MISSING_REQUIRED_FIELD:{dotted}", failures)
        for dotted in self.probe["MANDATORY_PRESENT_OBSERVATIONS"]:
            self.assertIn(f"MISSING_REQUIRED_FIELD:{dotted}", failures)

    # -- C02-T10 / C02-T11: frozen expected fill and Candidate-02 ---------

    def test_c02_t10_expected_fill_id_is_a_frozen_contract_constant(self) -> None:
        self.assertEqual(self.probe["EXPECTED_FILL_ID"], EXPECTED_FILL_ID)
        self.assertEqual(self.probe["production_expectations"]()["fill_id"], EXPECTED_FILL_ID)

    def test_c02_t11_candidate02_identities_are_frozen_contract_constants(self) -> None:
        expectations = self.probe["production_expectations"]()
        self.assertEqual(
            expectations["candidate_raw_sha256"],
            "4495ade7fed522bf17a202d6f5422f608765b65a4463121175695c862b3f904c",
        )
        self.assertEqual(
            expectations["candidate_semantic_sha256"],
            "e16c9219b495062647b82b9e8a4d5e9c1b98f3e54ce43f0044c1a85fea162bbb",
        )
        self.assertEqual(
            self.probe["CANDIDATE02_CONTRACT_VALUES"],
            {
                "reconciliation_read_deadline_ms": 30000,
                "create_max_sends": 0,
                "modify_replace_max_sends": 0,
                "ordinary_cancel_max_sends": 0,
                "automated_execution_max_sends": 0,
            },
        )

    def test_c02_t11_candidate02_contract_value_gate_fails_closed(self) -> None:
        check = self.probe["check_candidate02_contract_values"]
        good = dict(self.probe["CANDIDATE02_CONTRACT_VALUES"])
        self.assertEqual(check(good), [])
        for field in good:
            with self.subTest(field=field):
                observed = dict(good)
                observed[field] = 1 if observed[field] == 0 else 0
                self.assertEqual(check(observed), [f"CANDIDATE02_CONTRACT_VALUE_MISMATCH:{field}"])

    # -- C03: atomic exclusive result creation (pure primitive) ------------

    @staticmethod
    def _fingerprint(path: Path) -> tuple:
        st = os.stat(path)
        return (path.read_bytes(), hashlib.sha256(path.read_bytes()).hexdigest(), st.st_size, st.st_mtime_ns)

    def test_c03_t04_exclusive_create_writes_a_genuinely_new_file(self) -> None:
        create = self.probe["create_result_file_exclusive"]
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "new_result.json"
            payload = '{"schema":"x","output_sink":{"output_written":true}}\n'
            self.assertFalse(target.exists())
            self.assertIsNone(create(str(target), payload))
            self.assertEqual(target.read_text(encoding="utf-8"), payload)

    def test_c03_t02_t07_exclusive_create_refuses_ordinary_existing_file(self) -> None:
        create = self.probe["create_result_file_exclusive"]
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "existing.json"
            target.write_bytes(b"PRE-EXISTING OPERATOR FILE \x00\xff bytes\r\n")
            before = self._fingerprint(target)
            self.assertEqual(create(str(target), "REPLACEMENT PAYLOAD\n"), "OUTPUT_PATH_ALREADY_EXISTS")
            self.assertEqual(self._fingerprint(target), before)
            # An empty pre-existing file is refused too: no truncate-to-zero edge.
            empty = Path(tmp) / "empty.json"
            empty.write_bytes(b"")
            self.assertEqual(create(str(empty), "X\n"), "OUTPUT_PATH_ALREADY_EXISTS")
            self.assertEqual(empty.read_bytes(), b"")

    def test_c03_t01_exclusive_create_refuses_real_hard_link_to_protected_file(self) -> None:
        """A real NTFS hard link, not a mocked equality: the link and the
        'protected' file are two directory entries for ONE file object, so
        any write through the link would modify the protected bytes."""
        create = self.probe["create_result_file_exclusive"]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            protected = root / "protected_root" / "arb_execution_authority_v1.sqlite3"
            protected.parent.mkdir()
            protected.write_bytes(b"SQLite format 3\x00" + bytes(range(256)) * 8)
            outside = root / "safe_output"
            outside.mkdir()
            link = outside / "result.json"
            os.link(protected, link)
            self.assertTrue(os.path.samefile(protected, link))
            self.assertEqual(os.stat(protected).st_nlink, 2)
            # The path layer cannot see the alias: the link is outside the
            # protected root and is not a lexical or link-resolved alias.
            resolved, sink_failure = self.probe["classify_output_sink"](
                str(link), protected_roots=[str(protected.parent)], protected_files=[str(protected)],
            )
            self.assertIsNone(sink_failure)
            self.assertIsNotNone(resolved)
            before = self._fingerprint(protected)
            self.assertEqual(create(resolved, "TRUNCATING PAYLOAD\n"), "OUTPUT_PATH_ALREADY_EXISTS")
            self.assertEqual(self._fingerprint(protected), before)
            self.assertTrue(os.path.samefile(protected, link))
            self.assertEqual(os.stat(protected).st_nlink, 2)

    def test_c03_t07_exclusive_create_refuses_existing_directory(self) -> None:
        create = self.probe["create_result_file_exclusive"]
        with tempfile.TemporaryDirectory() as tmp:
            occupied = Path(tmp) / "result.json"
            (occupied / "child").mkdir(parents=True)
            failure = create(str(occupied), "X\n")
            self.assertIsNotNone(failure)
            self.assertTrue(failure == "OUTPUT_PATH_ALREADY_EXISTS"
                            or failure.startswith("OUTPUT_EXCLUSIVE_CREATE_FAILED:"), failure)
            self.assertEqual([p.name for p in occupied.iterdir()], ["child"])

    def test_c03_t07_failure_classifications_are_stable_constants(self) -> None:
        self.assertEqual(self.probe["OUTPUT_PATH_ALREADY_EXISTS"], "OUTPUT_PATH_ALREADY_EXISTS")
        self.assertEqual(self.probe["OUTPUT_EXCLUSIVE_CREATE_FAILED"], "OUTPUT_EXCLUSIVE_CREATE_FAILED")
        self.assertEqual(self.probe["OUTPUT_WRITE_FAILED"], "OUTPUT_WRITE_FAILED")

    def test_c03_t03_race_hook_itself_never_overwrites(self) -> None:
        hook = self.probe["_fixture_occupy_output_after_validation"]
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "raced.json"
            self.assertIsNone(hook(str(target)))
            self.assertEqual(target.read_bytes(), self.probe["FIXTURE_RACE_OBJECT_BYTES"])
            target.write_bytes(b"SOMETHING ELSE")
            self.assertEqual(hook(str(target)), "FIXTURE_RACE_HOOK_FAILED:FileExistsError")
            self.assertEqual(target.read_bytes(), b"SOMETHING ELSE")


class TestProductionParameterSurface(unittest.TestCase):
    """Structural proofs about what the production CLI surface CANNOT be
    asked to do. Supersedes CORRECTION_01 T21/T22 with a strictly stronger
    theorem: the predecessor argued that `-AuthorityPath`/`-LedgerPath`
    'only say where to read from'. Marco BLOCK defect 1 established that
    this is exactly the defect, so those parameters no longer exist."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.probe = _load_embedded_probe_module()
        cls.params = _ps1_declared_parameters()
        cls.probe_args = _probe_declared_arguments()

    def test_c02_t01_no_production_source_parameter_exists(self) -> None:
        """correction_01_theorem: T22 (superseded -- strictly stronger)."""
        for banned in ("repo", "authoritypath", "ledgerpath", "conflictdomain"):
            with self.subTest(parameter=banned):
                self.assertNotIn(banned, self.params)
        for banned in ("--repo", "--authority", "--ledger", "--conflict-domain"):
            with self.subTest(argument=banned):
                self.assertNotIn(banned, self.probe_args)

    def test_c02_t10_t11_no_production_expected_value_parameter_exists(self) -> None:
        for banned in ("fillid", "expectedcandidaterawsha256", "expectedcandidatesemanticsha256"):
            with self.subTest(parameter=banned):
                self.assertNotIn(banned, self.params)
        for banned in ("--fill-id", "--expected-candidate-raw-sha256", "--expected-candidate-semantic-sha256"):
            with self.subTest(argument=banned):
                self.assertNotIn(banned, self.probe_args)
        # No -Expected<FrozenField> style override for any frozen identity.
        flattened = _ps1_param_block().lower().replace("_", "")
        for key in self.probe["FROZEN_PRODUCTION_IDENTITY"]:
            camel = "".join(part.capitalize() for part in key.split("_"))
            self.assertNotIn(f"expected{camel}".lower(), flattened)

    def test_c02_t12_every_alternate_value_parameter_is_fixture_scoped(self) -> None:
        """correction_01_theorem: T21 (superseded). CORRECTION_01 proved 'no
        seam exists at all'. CORRECTION_02 adds an explicit Design B fixture
        seam, so the theorem becomes: every parameter that can substitute a
        frozen value is fixture-scoped by name, and the fixture cannot emit
        production PASS."""
        production_parameters = {"candidate02path", "python", "outputpath", "nonproductionfixturemode"}
        for name in self.params:
            if name in production_parameters:
                continue
            with self.subTest(parameter=name):
                self.assertTrue(name.startswith("fixture"), f"non-fixture override parameter -{name}")
        for argument in self.probe_args:
            if argument in {"--candidate02", "--output", "--canonical-commit", "--canonical-tree",
                            "--nonproduction-fixture-mode"}:
                continue
            with self.subTest(argument=argument):
                self.assertTrue(argument.startswith("--fixture-"), f"non-fixture override argument {argument}")

    def test_c02_t12_exit_zero_is_reserved_for_production(self) -> None:
        self.assertEqual(self.probe["EXIT_PRODUCTION_PASS"], 0)
        self.assertEqual(self.probe["EXIT_FIXTURE_COMPLETE"], 3)
        self.assertEqual(self.probe["EXIT_INCOMPLETE"], 1)
        self.assertEqual(self.probe["STATUS_PRODUCTION_PASS"], "READ_ONLY_REVALIDATION_PASS")
        self.assertNotEqual(self.probe["STATUS_FIXTURE_COMPLETE"], self.probe["STATUS_PRODUCTION_PASS"])
        # The launcher prints the production terminal marker only for exit 0.
        text = LAUNCHER_PATH.read_text(encoding="utf-8")
        match = re.search(
            r'if \(\$ProbeExit -eq 0\) \{\s*\r?\n\s*Write-Output "READ_ONLY_REVALIDATION_TERMINAL=PASS"', text,
        )
        self.assertIsNotNone(match, "production PASS marker must be guarded by exit code 0 alone")
        self.assertEqual(text.count('READ_ONLY_REVALIDATION_TERMINAL=PASS"'), 1)

    def test_c02_t03_default_output_sink_is_not_psscriptroot(self) -> None:
        text = LAUNCHER_PATH.read_text(encoding="utf-8")
        default_block = re.search(r"if \(-not \$OutputPath\) \{(.*?)\}", text, re.DOTALL)
        self.assertIsNotNone(default_block)
        self.assertNotIn("PSScriptRoot", default_block.group(1))
        self.assertIn("GetTempPath", default_block.group(1))
        # Nothing anywhere in the launcher may default a result sink to the
        # script's own (repository-resident) directory.
        self.assertNotIn("Join-Path $PSScriptRoot", text)

    def test_c03_t01_t06_result_is_written_only_through_one_exclusive_create(self) -> None:
        """Static half of the exclusive-create theorem. The single result
        write site is an `open(path, "x")`; there is no truncating write, no
        existence-check-then-write sequence, and no retry around creation."""
        source = _extract_embedded_probe_source()
        self.assertEqual(source.count('open(path, "x", encoding="utf-8")'), 1)
        self.assertEqual(source.count("def create_result_file_exclusive("), 1)
        self.assertEqual(len(re.findall(r"=\s*create_result_file_exclusive\(", source)), 1, "exactly one call site")
        for banned in ("Path(sink_resolved).write_text", ".write_bytes(", 'open(path, "w', "os.replace(",
                       "os.rename(", "os.unlink(", ".unlink(", "shutil.move(", "O_TRUNC"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, source)
        # No loop encloses the create call (no retry after failure).
        call = source.index("create_failure = create_result_file_exclusive(")
        preceding = source[source.rindex("\n    if sink_failure is None and sink_resolved is not None:", 0, call):call]
        self.assertNotRegex(preceding, r"\bfor\b|\bwhile\b")

    def test_c03_wrapper_never_stats_or_reads_a_refused_output_path(self) -> None:
        """The PowerShell post-probe report may only touch a file the probe
        reports it created. The predecessor's `Test-Path` on the requested
        pathname could stat a path under the deployed-state root after a
        refused sink, or hash a pre-existing object such as a hard link."""
        text = LAUNCHER_PATH.read_text(encoding="utf-8")
        self.assertNotIn("Test-Path -LiteralPath $OutputPath", text)
        self.assertIn('$ProbeLine.Contains(\'"output_written":true\')', text)
        gate = text.index("if ($ProbeCreatedResultFile) {")
        self.assertLess(gate, text.index("[System.IO.File]::ReadAllBytes($OutputPath)"))

    def test_c01_t18_no_retry_loop_exists(self) -> None:
        """correction_01_theorem: T18 static half (preserved unchanged)."""
        source = LAUNCHER_PATH.read_text(encoding="utf-8")
        self.assertIn('Write-Output "AUTOMATIC_RETRIES=0"', source)
        self.assertNotRegex(
            _extract_embedded_probe_source(),
            r"for\s+_?attempt\s+in\s+range|while\s+True.*retry",
            "embedded probe source must contain no retry loop",
        )

    def test_c01_sqlite_access_is_mode_ro_only(self) -> None:
        """correction_01_theorem: preserved SQLite mode=ro invariant."""
        source = _extract_embedded_probe_source()
        self.assertIn('as_uri() + "?mode=ro"', source)
        self.assertEqual(source.count("sqlite3.connect("), 1)
        # The read-write "open + catch up" family must never be INVOKED. The
        # names legitimately appear in the module docstring, which explains
        # at length why they are deliberately avoided, so the theorem is
        # about call sites rather than mere textual presence.
        for banned in ("_open_locked(", "read_active_local_safety_state_v1(",
                       "acquire_normal_writer_candidate_v1(", "append_batch("):
            with self.subTest(banned=banned):
                self.assertEqual(source.count(banned), 0, f"embedded probe must not call {banned}")


def _clock_pair():
    state = {"t": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)}

    def clock():
        v = state["t"]
        state["t"] += timedelta(microseconds=1)
        return v
    return clock


def _uuid_factory():
    state = {"n": 1}

    def factory():
        v = uuid.UUID(int=state["n"], version=4)
        state["n"] += 1
        return v
    return factory


_SYNTHETIC_RISK_CONFIG_OBJECT_TEMPLATE = {
    "schema_version": 1,
    "currency": "USD",
    "per_order": {
        "max_contracts": "10.00", "max_worst_case_exposure_usd": "10.00",
        "price_reasonability_required": True, "max_abs_reference_price_deviation_usd": "0.10",
        "max_market_data_age_ms": 1000,
    },
    "per_market": {
        "max_abs_net_position_contracts": "20.00", "max_gross_exposure_usd": "20.00",
        "max_authoritative_working_orders": 10, "max_working_contracts": "20.00",
        "max_working_order_exposure_usd": "20.00",
    },
    "conflict_domain_account": {
        "max_aggregate_exposure_usd": "100.00", "max_aggregate_working_orders": 50,
        "max_aggregate_working_contracts": "100.00", "max_unresolved_write_count": 0,
        "max_conservative_unresolved_write_exposure_usd": "0.00",
    },
    "flow": {
        "create_max_sends": 0, "create_window_ms": 1000, "modify_replace_max_sends": 0,
        "modify_replace_window_ms": 1000, "ordinary_cancel_max_sends": 0, "ordinary_cancel_window_ms": 1000,
        "automated_execution_max_sends": 0, "automated_execution_window_ms": 1000,
        "emergency_cancel_max_sends": 2, "emergency_cancel_window_ms": 1000,
        "emergency_cancel_max_in_flight": 1, "emergency_cancel_request_deadline_ms": 500,
        "emergency_retry_max_attempts_per_target_per_action": 1,
        "emergency_backoff_base_ms": 10, "emergency_backoff_max_ms": 100,
    },
    "state_integrity": {
        "max_reconciliation_lag_ms": 1000, "max_required_market_data_age_ms": 1000,
        "max_future_wall_clock_skew_ms": 10, "max_reconciliation_attempts_per_cycle": 1,
        "reconciliation_read_deadline_ms": 30000, "reconciliation_backoff_base_ms": 10,
        "reconciliation_backoff_max_ms": 100,
    },
    "venue_defense": {
        "order_group_mode": "NOT_REQUIRED", "required_order_group_id": None,
        "cancel_order_on_pause_required": True, "reduce_only_policy": "NO_SAFETY_CREDIT",
        "post_only_policy": "NO_SAFETY_CREDIT",
    },
}


def _write_synthetic_candidate(path: Path, *, conflict_domain: str) -> None:
    obj = dict(_SYNTHETIC_RISK_CONFIG_OBJECT_TEMPLATE)
    obj["conflict_domain"] = conflict_domain
    path.write_text(json.dumps(obj), encoding="utf-8")


def _candidate_identity(path: Path) -> tuple:
    raw = path.read_bytes()
    raw_sha256 = hashlib.sha256(raw).hexdigest()
    config = _load_sha_bound_risk_config(path=str(path), expected_sha256=raw_sha256)
    return raw_sha256, config.sha256


class _V2FixtureCase(unittest.TestCase):
    """Base class providing a fresh synthetic active-domain N1 fixture per
    test, built with the same canonical helpers the accepted ledger-binding
    test suite already uses. Never touches deployed N1 state."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.probe = _load_embedded_probe_module()

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.clock = _clock_pair()
        self.uuidf = _uuid_factory()
        authority_root = self.tmp / "authority"
        authority_root.mkdir()
        self.binding = AuthorityNamespaceBinding.bind(
            authority_namespace_id="v2-test-ns", authority_namespace_root=authority_root,
            canonical_repository_root=str(REPO_ROOT),
        )
        initialize_authority_namespace(self.binding, clock=self.clock, uuid_factory=self.uuidf)
        self.domain_binding = lb.ExecutionDomainBindingV1(
            venue="KALSHI", environment="KALSHI_DEMO", account_scope_ref=ACCOUNT,
            subaccount=1, exchange_index=0,
        )
        self.conflict_domain = self.domain_binding.conflict_domain_ref

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _bootstrap(self, **overrides) -> lb.DomainBootstrapContractV1:
        kwargs = dict(
            binding=self.domain_binding, bootstrap_class="KNOWN_NONEMPTY_PRESTACK",
            bootstrap_cutoff_at_utc="2026-09-01T00:00:00.000000Z",
            prestack_activity_completeness="COMPLETE_KNOWN_NONEMPTY_PRESTACK",
            unresolved_write_count=0, unresolved_cancel_count=0,
            working_order_truth="COMPLETE_ZERO", fill_truth="COMPLETE_KNOWN_NONZERO",
            position_truth="COMPLETE_KNOWN_NONZERO",
            retained_position_ticker="KXAAAGASD-26SEP02-4.1200",
            retained_position_floor_contracts=Decimal("1.00"),
        )
        kwargs.update(overrides)
        return lb.DomainBootstrapContractV1(**kwargs)

    def build_ledger(self, *, include_expected_fill: bool, ledger_name: str = "ledger.sqlite3",
                      close_session: bool = True, fault_hook=None) -> dict:
        bootstrap = self._bootstrap()
        ledger_path = self.tmp / ledger_name
        row, contract = lb.initialize_active_execution_domain_ledger(
            self.binding, canonical_repository_root=str(REPO_ROOT), domain_binding=self.domain_binding,
            bootstrap_contract=bootstrap, ledger_path=str(ledger_path), clock=self.clock, uuid_factory=self.uuidf,
        )
        session_id = None
        if include_expected_fill:
            acquisition = lb.acquire_active_emergency_control_only_v1(
                self.binding, canonical_repository_root=str(REPO_ROOT), active_contract=contract,
                expected_ledger_path=str(ledger_path), clock=self.clock, uuid_factory=self.uuidf,
                fault_hook=fault_hook,
            )
            self.assertIsNotNone(acquisition.handle, acquisition.failure_code)
            handle = acquisition.handle
            session_id = handle.restricted_session_id
            canonical_order = {
                "order_id": "order-1", "status": "cancelled", "remaining_count_fp": "0.00",
                "market": "KXAAAGASD-26SEP02-4.1200", "outcome_side": "YES",
                "yes_price": Decimal("0.50"), "cancel_order_on_pause": False,
            }
            handle.record_order_observation({
                "venue_order_id": "order-1", "client_order_id": "client-order-1",
                "source_request_id": "req-order-1", "source_operation": "GET_ORDER_V2",
                "venue_payload_schema_id": "order-v1", "canonical_venue_payload": canonical_order,
                "canonical_venue_payload_sha256": hashlib.sha256(canonical_json_bytes(canonical_order)).hexdigest(),
                "observation_semantic_class": "AUTHORITATIVE_ACTIVE_ORDER",
            })
            canonical_fill = lb.canonical_kalshi_fill_payload(
                fill_id=EXPECTED_FILL_ID, order_id="order-1",
                price=Decimal("0.5000"), quantity=Decimal("1.00"), fee=Decimal("0.017500"),
                additional_fields={
                    "market": "KXAAAGASD-26SEP02-4.1200", "outcome_side": "YES",
                    "authoritative_created_time_utc": "2026-09-01T23:34:43.231843Z",
                },
            )
            handle.record_fill_observation({
                "canonical_venue_payload": canonical_fill,
                "canonical_venue_payload_sha256": hashlib.sha256(canonical_json_bytes(canonical_fill)).hexdigest(),
                "client_order_id": "client-order-1", "source_operation": "SYNTHETIC_FILL_READ",
                "source_request_id": "req-fill-1", "venue_fill_id": EXPECTED_FILL_ID,
                "venue_order_id": "order-1", "venue_payload_schema_id": "fill-v1",
            })
            if close_session:
                handle.close()
            else:
                # Leave connections open without emitting RESTRICTED_SESSION_ENDED,
                # simulating an interrupted process.
                raw_locked = getattr(handle, "_EmergencyControlLedgerHandle__locked")
                raw_locked.ledger.close()
                raw_locked.authority.close()
        candidate_path = self.tmp / "candidate.json"
        _write_synthetic_candidate(candidate_path, conflict_domain=self.conflict_domain)
        raw_sha256, semantic_sha256 = _candidate_identity(candidate_path)
        return {
            "authority_path": str(self.binding.authority_store_resolved_path),
            "ledger_path": str(ledger_path),
            "candidate_path": str(candidate_path),
            "raw_sha256": raw_sha256,
            "semantic_sha256": semantic_sha256,
            "session_id": session_id,
            "contract": contract,
        }

    # -- launcher invocation ------------------------------------------------

    def run_launcher_raw(self, fx: dict, *, output_name: str | None = "result.json",
                         identity_path: str | None = None, null_observations=(),
                         race_occupy: bool = False, **overrides) -> tuple:
        """Invoke the delivered launcher in its explicitly nonproduction
        fixture mode and return `(result, exit_code, stdout)`.

        This helper deliberately offers no way to build a production-mode
        command line: a production invocation would read the frozen deployed
        N1 topology, which this task is not authorized to touch."""
        args = [
            PWSH, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-File", str(LAUNCHER_PATH),
            "-Candidate02Path", overrides.get("candidate_path", fx["candidate_path"]),
            "-NonProductionFixtureMode",
            "-FixtureRepo", overrides.get("repo", str(REPO_ROOT)),
            "-FixtureAuthorityPath", overrides.get("authority_path", fx["authority_path"]),
            "-FixtureLedgerPath", overrides.get("ledger_path", fx["ledger_path"]),
            "-FixtureConflictDomain", overrides.get("conflict_domain", self.conflict_domain),
            "-FixtureExpectedCandidateRawSha256", overrides.get("expected_raw_sha256", fx["raw_sha256"]),
            "-FixtureExpectedCandidateSemanticSha256", overrides.get("expected_semantic_sha256", fx["semantic_sha256"]),
        ]
        if output_name is not None:
            args += ["-OutputPath", overrides.get("output_path", str(self.tmp / output_name))]
        elif "output_path" in overrides:
            args += ["-OutputPath", overrides["output_path"]]
        if "fill_id" in overrides:
            args += ["-FixtureFillId", overrides["fill_id"]]
        if identity_path is not None:
            args += ["-FixtureExpectedIdentityPath", identity_path]
        for dotted in null_observations:
            args += ["-FixtureDropObservation", dotted]
        if race_occupy:
            args += ["-FixtureRaceOccupyOutputBeforeCreate"]
        proc = subprocess.run(args, capture_output=True, text=True, timeout=180)
        stdout = proc.stdout
        json_line = None
        for line in stdout.splitlines():
            line = line.strip()
            if line.startswith("{") and '"schema"' in line:
                json_line = line
                break
        self.assertIsNotNone(json_line, f"no JSON result line in stdout:\n{stdout}\n---stderr---\n{proc.stderr}")
        return json.loads(json_line), proc.returncode, stdout

    def run_launcher(self, fx: dict, **kwargs) -> tuple:
        result, exit_code, _ = self.run_launcher_raw(fx, **kwargs)
        return result, exit_code

    def bind_fixture_identity(self, result: dict) -> str:
        """Write the synthetic fixture's own observed identity to a temp file
        so a follow-up fixture invocation can bind against it. Two steps by
        design: the launcher never derives an expected identity from what it
        just observed within a single run."""
        observed = dict(result["identity"])
        observed.update(result["domain"])
        expected = {key: observed[key] for key in self.probe["FROZEN_PRODUCTION_IDENTITY"]}
        path = self.tmp / "fixture_identity.json"
        path.write_text(json.dumps(expected), encoding="utf-8")
        return str(path)

    def run_bound_fixture(self, fx: dict, **kwargs) -> tuple:
        """Two-step fixture invocation that reaches the complete
        nonproduction result: observe, bind the observed identity, re-run."""
        first, _ = self.run_launcher(fx, output_name="probe_result.json")
        identity_path = self.bind_fixture_identity(first)
        return self.run_launcher_raw(fx, identity_path=identity_path, **kwargs)


MANDATORY_ENVELOPE_GROUPS = (
    ("mode", ("observation_mode", "production_pass_eligible", "nonproduction_fixture_marker",
              "fixture_overrides")),
    ("identity", ("authority_namespace_id", "authority_instance_id", "authority_schema_revision",
                  "authority_path", "authority_store_path_identity_sha256", "ledger_instance_id",
                  "ledger_schema_revision", "ledger_path", "ledger_path_identity_sha256",
                  "conflict_domain_ref")),
    ("source_binding", ("expected_repo_path", "expected_authority_source_path",
                        "expected_ledger_source_path", "resolved_repo_path",
                        "resolved_authority_source_path", "resolved_ledger_source_path",
                        "repo_source_bound", "authority_source_bound", "ledger_source_bound")),
    ("output_sink", ("requested_output_path", "resolved_output_path", "output_sink_safe",
                     "output_written")),
    ("tail", ("authority_ledger_relation", "authority_trusted_sequence", "authority_trusted_event_hash",
              "ledger_terminal_sequence", "ledger_terminal_event_hash")),
    ("domain", ("execution_domain_binding_id", "execution_domain_binding_sha256", "bootstrap_contract_sha256",
                "active_contract_id", "active_contract_sha256", "incident_id", "writer_proof_id",
                "conflict_domain_ref")),
    ("risk_writer", ("risk_control_state", "risk_state_epoch", "writer_proof_state",
                     "writer_proof_release_eligible", "normal_writer_eligible")),
    ("sessions", ("active_writer_session_id", "active_restricted_session_id",
                  "abnormal_writer_session_ids", "abnormal_restricted_session_ids")),
    ("unresolved", ("unresolved_write_request_ids", "unresolved_write_count",
                    "unresolved_cancel_attempt_ids", "unresolved_cancel_count",
                    "fill_conflicts", "fill_conflict_count")),
    ("local_projection", ("local_trusted_working_order_count", "local_trusted_working_order_ids",
                          "trusted_filled_exposure", "retained_position_evidence",
                          "release_universe_conflict_ids")),
    ("durable_fill", ("durable_fill_ids", "expected_fill_id", "expected_fill_present_count",
                      "expected_fill_present_and_exact", "matching_event_ids", "matched_fields")),
    ("activity", ("network_activity", "credential_activity", "kalshi_access", "venue_writes",
                  "repository_writes", "persistent_state_writes", "restricted_session_append",
                  "risk_config_consumption", "writer_release", "production")),
    ("mutation_proof", ("authority_before", "authority_after", "ledger_before", "ledger_after",
                        "authority_unchanged", "ledger_unchanged")),
)


def _assert_complete_envelope_shape(test: unittest.TestCase, result: dict) -> None:
    for key in (
        "schema", "task_id", "observation_timestamp_utc", "canonical_main_commit", "canonical_main_tree",
        "mode", "identity", "source_binding", "output_sink", "tail", "domain", "risk_writer", "sessions",
        "unresolved", "local_projection", "durable_fill", "candidate02", "activity", "mutation_proof",
        "observation_completeness", "status",
    ):
        test.assertIn(key, result, f"missing mandatory top-level key: {key}")
    for group, keys in MANDATORY_ENVELOPE_GROUPS:
        test.assertIn(group, result)
        test.assertIsInstance(result[group], dict, f"group {group} must be a dict even on failure")
        for key in keys:
            test.assertIn(key, result[group], f"missing mandatory key {group}.{key}")


def _assert_not_production_pass(test: unittest.TestCase, result: dict, exit_code: int, stdout: str = "") -> None:
    """Every end-to-end invocation in this module must fail this assertion's
    negation: no fixture run, however green, may emit production PASS."""
    test.assertNotEqual(exit_code, 0)
    test.assertNotEqual(result["status"], "READ_ONLY_REVALIDATION_PASS")
    test.assertEqual(result["mode"]["observation_mode"], "NONPRODUCTION_TEST_FIXTURE")
    test.assertFalse(result["mode"]["production_pass_eligible"])
    test.assertEqual(
        result["mode"]["nonproduction_fixture_marker"],
        "NONPRODUCTION_TEST_FIXTURE_RESULT_NOT_A_PRODUCTION_OBSERVATION",
    )
    if stdout:
        test.assertNotIn("READ_ONLY_REVALIDATION_TERMINAL=PASS", stdout)


@unittest.skipUnless(PWSH, "powershell.exe/pwsh not available on PATH")
class TestV2LauncherEndToEnd(_V2FixtureCase):

    # -- C02-T12 / preserved happy path ------------------------------------

    def test_c02_t12_bound_fixture_completes_but_cannot_emit_production_pass(self) -> None:
        """The strongest positive end-to-end evidence this task can produce
        offline: a fully valid synthetic fixture, bound to its own observed
        identity, satisfies every gate the launcher can evaluate -- and is
        STILL structurally incapable of the production terminal PASS."""
        fx = self.build_ledger(include_expected_fill=True)
        result, exit_code, stdout = self.run_bound_fixture(fx)
        _assert_complete_envelope_shape(self, result)
        self.assertEqual(
            result["observation_completeness"]["failures"], [],
            result["observation_completeness"]["failures"],
        )
        self.assertTrue(result["observation_completeness"]["complete"])
        self.assertEqual(result["status"], "NONPRODUCTION_FIXTURE_COMPLETE")
        self.assertEqual(exit_code, 3)
        _assert_not_production_pass(self, result, exit_code, stdout)
        self.assertIn("READ_ONLY_REVALIDATION_TERMINAL=NONPRODUCTION_FIXTURE_NO_PRODUCTION_PASS", stdout)
        self.assertIn("OBSERVATION_MODE=NONPRODUCTION_TEST_FIXTURE", stdout)
        # The V1 completeness gap fields are genuinely observed.
        for dotted in C02_T09_REQUIRED_MANDATORY_PATHS:
            present, value = self.probe["lookup_observation"](result, dotted)
            self.assertTrue(present and value is not None, dotted)
        # Historical tail 16 is not hard-coded: this fixture's own tail is reported.
        self.assertEqual(result["tail"]["ledger_terminal_sequence"], 7)
        self.assertEqual(result["tail"]["authority_ledger_relation"], "AUTHORITY_EQUAL_TO_LEDGER")
        for value in result["activity"].values():
            self.assertEqual(value, "NONE")
        self.assertTrue(result["mutation_proof"]["authority_unchanged"])
        self.assertTrue(result["mutation_proof"]["ledger_unchanged"])

    def test_c01_t22_unbound_synthetic_fixture_fails_frozen_identity_gate(self) -> None:
        """correction_01_theorem: T22 end-to-end half (preserved). A synthetic
        fixture that does NOT declare a fixture identity is still measured
        against the frozen accepted N1 identity and fails closed."""
        fx = self.build_ledger(include_expected_fill=True)
        result, exit_code, stdout = self.run_launcher_raw(fx)
        _assert_complete_envelope_shape(self, result)
        _assert_not_production_pass(self, result, exit_code, stdout)
        self.assertEqual(result["status"], "RESULT_SCHEMA_INCOMPLETE")
        mismatches = [
            f for f in result["observation_completeness"]["failures"]
            if f.startswith("PRODUCTION_IDENTITY_MISMATCH:")
        ]
        self.assertTrue(mismatches, result["observation_completeness"]["failures"])
        self.assertEqual(result["observation_completeness"]["failures"], mismatches)

    # -- C02-T01 / C02-T02 end-to-end --------------------------------------

    def test_c02_t01_default_invocation_rejects_fixture_overrides(self) -> None:
        """A default (production) invocation that is nonetheless handed a
        fixture override must reject it rather than honour it, perform no
        state read, and fail closed."""
        fx = self.build_ledger(include_expected_fill=True)
        args = [
            PWSH, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-File", str(LAUNCHER_PATH),
            "-Candidate02Path", fx["candidate_path"],
            "-OutputPath", str(self.tmp / "refused.json"),
            "-FixtureFillId", "00000000-0000-0000-0000-000000000000",
        ]
        proc = subprocess.run(args, capture_output=True, text=True, timeout=180)
        self.assertNotEqual(proc.returncode, 0)
        self.assertNotIn("READ_ONLY_REVALIDATION_TERMINAL=PASS", proc.stdout)
        result = None
        for line in proc.stdout.splitlines():
            line = line.strip()
            if line.startswith("{") and '"schema"' in line:
                result = json.loads(line)
                break
        self.assertIsNotNone(result, proc.stdout + proc.stderr)
        _assert_complete_envelope_shape(self, result)
        self.assertEqual(result["mode"]["observation_mode"], "PRODUCTION")
        self.assertEqual(result["status"], "RESULT_SCHEMA_INCOMPLETE")
        self.assertTrue(
            any(f.startswith("FIXTURE_OVERRIDE_WITHOUT_FIXTURE_MODE")
                for f in result["observation_completeness"]["failures"]),
            result["observation_completeness"]["failures"],
        )
        # The refusal short-circuits before any state read: no store was opened.
        self.assertIsNone(result["identity"]["authority_namespace_id"])
        self.assertIsNone(result["mutation_proof"]["authority_before"])

    def test_c02_t02_copied_stores_at_alternate_paths_cannot_reach_production_pass(self) -> None:
        """Byte-identical copies of an internally valid store set, read from
        a different filesystem location, keep every embedded metadata
        identity -- and still cannot produce a production result, because the
        only route to those paths is the nonproduction fixture seam."""
        fx = self.build_ledger(include_expected_fill=True)
        copies = self.tmp / "copies"
        copies.mkdir()
        copied_authority = copies / "authority_copy.sqlite3"
        copied_ledger = copies / "ledger_copy.sqlite3"
        shutil.copyfile(fx["authority_path"], copied_authority)
        shutil.copyfile(fx["ledger_path"], copied_ledger)
        first, _ = self.run_launcher(fx, output_name="probe_result.json")
        identity_path = self.bind_fixture_identity(first)
        result, exit_code, stdout = self.run_launcher_raw(
            fx, identity_path=identity_path, output_name="copy_result.json",
            authority_path=str(copied_authority), ledger_path=str(copied_ledger),
        )
        _assert_complete_envelope_shape(self, result)
        # The embedded metadata identities survived the copy verbatim...
        observed = dict(result["identity"])
        observed.update(result["domain"])
        self.assertEqual(
            self.probe["check_frozen_production_identity"](
                observed, json.loads(Path(identity_path).read_text(encoding="utf-8"))),
            [],
        )
        self.assertEqual(result["identity"]["authority_path"], first["identity"]["authority_path"])
        # ...yet the run is unambiguously nonproduction and cannot PASS.
        _assert_not_production_pass(self, result, exit_code, stdout)
        self.assertEqual(
            result["source_binding"]["resolved_authority_source_path"],
            str(copied_authority.resolve()),
        )

    # -- C02-T03 to C02-T06: output sink safety end-to-end -----------------

    def test_c02_t03_default_sink_is_outside_repo_and_deployment_state(self) -> None:
        fx = self.build_ledger(include_expected_fill=True)
        before = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "status", "--porcelain=v1", "--untracked-files=all"],
            capture_output=True, text=True, check=True,
        ).stdout
        result, exit_code, stdout = self.run_launcher_raw(fx, output_name=None)
        after = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "status", "--porcelain=v1", "--untracked-files=all"],
            capture_output=True, text=True, check=True,
        ).stdout
        self.assertEqual(before, after, "a no-OutputPath invocation must leave the repository untouched")
        self.assertIn("DEFAULT_RESULT_SINK_USED=True", stdout)
        written = Path(result["output_sink"]["resolved_output_path"])
        try:
            self.assertTrue(result["output_sink"]["output_sink_safe"])
            self.assertTrue(result["output_sink"]["output_written"])
            self.assertTrue(written.is_file())
            norm = self.probe["normalize_for_compare"]
            within = self.probe["is_within_root"]
            # Both sides resolved: Windows reports the user temp root in 8.3
            # short form to one process and long form to another.
            self.assertTrue(
                within(norm(str(written.resolve())), norm(str(Path(tempfile.gettempdir()).resolve())))
            )
            for protected in (str(REPO_ROOT), EXPECTED_FROZEN_SOURCES["repo"], EXPECTED_FROZEN_DEPLOYMENT_ROOT):
                self.assertFalse(within(norm(str(written)), norm(protected)), protected)
            # The file written is the same logical result emitted on stdout.
            self.assertEqual(json.loads(written.read_text(encoding="utf-8")), result)
        finally:
            written.unlink(missing_ok=True)

    def test_c02_t04_explicit_output_under_repository_fails_closed(self) -> None:
        fx = self.build_ledger(include_expected_fill=True)
        target = REPO_ROOT / "__c02_sink_guard_must_never_create_this__.json"
        self.assertFalse(target.exists())
        before = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "status", "--porcelain=v1", "--untracked-files=all"],
            capture_output=True, text=True, check=True,
        ).stdout
        result, exit_code, stdout = self.run_launcher_raw(fx, output_name=None, output_path=str(target))
        try:
            _assert_complete_envelope_shape(self, result)
            _assert_not_production_pass(self, result, exit_code, stdout)
            self.assertFalse(result["output_sink"]["output_sink_safe"])
            self.assertFalse(result["output_sink"]["output_written"])
            self.assertTrue(
                any(f.startswith("UNSAFE_OUTPUT_SINK:PROTECTED_ROOT")
                    for f in result["observation_completeness"]["failures"]),
                result["observation_completeness"]["failures"],
            )
            self.assertFalse(target.exists(), "the guard must create nothing at an unsafe sink")
            after = subprocess.run(
                ["git", "-C", str(REPO_ROOT), "status", "--porcelain=v1", "--untracked-files=all"],
                capture_output=True, text=True, check=True,
            ).stdout
            self.assertEqual(before, after)
        finally:
            target.unlink(missing_ok=True)

    def test_c02_t05_explicit_output_under_deployment_state_fails_closed(self) -> None:
        """The deployed-state root is refused by the guard's purely lexical
        first layer, so this test performs zero filesystem access on
        `C:\\b1\\kals\\arb_state` -- it never creates, opens, or even stats a
        path beneath it."""
        fx = self.build_ledger(include_expected_fill=True)
        target = EXPECTED_FROZEN_DEPLOYMENT_ROOT + "\\__c02_sink_guard_must_never_create_this__\\result.json"
        result, exit_code, stdout = self.run_launcher_raw(fx, output_name=None, output_path=target)
        _assert_complete_envelope_shape(self, result)
        _assert_not_production_pass(self, result, exit_code, stdout)
        self.assertFalse(result["output_sink"]["output_sink_safe"])
        self.assertFalse(result["output_sink"]["output_written"])
        self.assertIn(
            f"UNSAFE_OUTPUT_SINK:PROTECTED_ROOT:{EXPECTED_FROZEN_DEPLOYMENT_ROOT}",
            result["observation_completeness"]["failures"],
        )
        self.assertIn("RESULT_WRITTEN=NONE", stdout)

    def test_c02_t06_output_alias_of_protected_input_fails_closed(self) -> None:
        fx = self.build_ledger(include_expected_fill=True)
        for label, target in (
            ("authority", fx["authority_path"]),
            ("ledger", fx["ledger_path"]),
            ("candidate02", fx["candidate_path"]),
            ("launcher", str(LAUNCHER_PATH)),
        ):
            with self.subTest(label=label):
                before = Path(target).read_bytes()
                result, exit_code, stdout = self.run_launcher_raw(
                    fx, output_name=None, output_path=target,
                )
                _assert_complete_envelope_shape(self, result)
                _assert_not_production_pass(self, result, exit_code, stdout)
                self.assertFalse(result["output_sink"]["output_sink_safe"])
                self.assertFalse(result["output_sink"]["output_written"])
                self.assertTrue(
                    any(f.startswith("UNSAFE_OUTPUT_SINK:PROTECTED")
                        for f in result["observation_completeness"]["failures"]),
                    result["observation_completeness"]["failures"],
                )
                self.assertEqual(Path(target).read_bytes(), before,
                                 "an aliased protected input must not be modified")

    # -- C02-T07 / C02-T08: mutation proof on failing readable paths -------

    def _assert_full_mutation_proof(self, result: dict) -> None:
        proof = result["mutation_proof"]
        for store in ("authority", "ledger"):
            self.assertIsNotNone(proof[f"{store}_before"], f"{store}_before")
            self.assertIsNotNone(proof[f"{store}_after"], f"{store}_after")
            self.assertTrue(proof[f"{store}_unchanged"], f"{store}_unchanged")
            self.assertEqual(proof[f"{store}_before"], proof[f"{store}_after"])

    def test_c02_t07_readable_schema_or_integrity_failure_still_proves_mutation(self) -> None:
        """correction_01_theorem: T18 runtime half (preserved and
        strengthened). A readable but structurally invalid ledger returns
        before any identity/replay work, and the before/after proof must
        still be captured for BOTH readable stores."""
        fx = self.build_ledger(include_expected_fill=True)
        corrupt_ledger = self.tmp / "corrupt_ledger.sqlite3"
        corrupt_ledger.write_bytes(b"not a real sqlite database file")
        before_bytes = corrupt_ledger.read_bytes()
        result, exit_code, stdout = self.run_launcher_raw(fx, ledger_path=str(corrupt_ledger))
        _assert_complete_envelope_shape(self, result)
        _assert_not_production_pass(self, result, exit_code, stdout)
        self.assertTrue(
            any(f.startswith("LEDGER_SCHEMA_OR_INTEGRITY_FAILED") or f.startswith("LEDGER_STORE_OPEN_FAILED")
                for f in result["observation_completeness"]["failures"]),
            result["observation_completeness"]["failures"],
        )
        self._assert_full_mutation_proof(result)
        self.assertEqual(corrupt_ledger.read_bytes(), before_bytes)

    def test_c02_t07_authority_schema_failure_still_proves_mutation(self) -> None:
        fx = self.build_ledger(include_expected_fill=True)
        corrupt_authority = self.tmp / "corrupt_authority.sqlite3"
        corrupt_authority.write_bytes(b"also not a real sqlite database file")
        result, exit_code, stdout = self.run_launcher_raw(fx, authority_path=str(corrupt_authority))
        _assert_complete_envelope_shape(self, result)
        _assert_not_production_pass(self, result, exit_code, stdout)
        self.assertTrue(
            any(f.startswith("AUTHORITY_SCHEMA_OR_INTEGRITY_FAILED") or f.startswith("AUTHORITY_STORE_OPEN_FAILED")
                for f in result["observation_completeness"]["failures"]),
            result["observation_completeness"]["failures"],
        )
        self._assert_full_mutation_proof(result)

    def test_c02_t08_candidate_and_identity_mismatch_still_prove_mutation(self) -> None:
        """correction_01_theorem: T19 (preserved and strengthened) plus
        T17 (preserved). Failures discovered AFTER a successful state read
        must not bypass the post-read proof either."""
        fx = self.build_ledger(include_expected_fill=True)
        first, _ = self.run_launcher(fx, output_name="probe_result.json")
        identity_path = self.bind_fixture_identity(first)
        cases = (
            ("candidate_raw_mismatch", {"expected_raw_sha256": "0" * 64}, "CANDIDATE02_RAW_SHA256_MISMATCH"),
            ("candidate_semantic_mismatch", {"expected_semantic_sha256": "0" * 64},
             "CANDIDATE02_SEMANTIC_SHA256_MISMATCH"),
            ("identity_mismatch", {}, "PRODUCTION_IDENTITY_MISMATCH:authority_namespace_id"),
            ("missing_expected_fill", {"fill_id": "00000000-0000-0000-0000-000000000000"},
             "EXPECTED_DURABLE_FILL_THEOREM_FAILED"),
        )
        for label, overrides, expected_failure in cases:
            with self.subTest(label=label):
                authority_before = Path(fx["authority_path"]).read_bytes()
                ledger_before = Path(fx["ledger_path"]).read_bytes()
                kwargs = dict(overrides)
                if label != "identity_mismatch":
                    kwargs["identity_path"] = identity_path
                result, exit_code, stdout = self.run_launcher_raw(
                    fx, output_name=f"{label}.json", **kwargs)
                _assert_complete_envelope_shape(self, result)
                _assert_not_production_pass(self, result, exit_code, stdout)
                self.assertIn(expected_failure, result["observation_completeness"]["failures"])
                self._assert_full_mutation_proof(result)
                self.assertEqual(Path(fx["authority_path"]).read_bytes(), authority_before)
                self.assertEqual(Path(fx["ledger_path"]).read_bytes(), ledger_before)

    def test_c01_t15_t16_missing_store_emits_complete_envelope_without_fabricated_proof(self) -> None:
        """correction_01_theorem: T15/T16 (preserved and strengthened). A
        missing file cannot have a before/after proof; the correction
        requires that gap stay explicitly classified rather than fabricated."""
        fx = self.build_ledger(include_expected_fill=True)
        for label, overrides, prefix, absent in (
            ("authority", {"authority_path": str(self.tmp / "absent_authority.sqlite3")},
             "AUTHORITY_STORE_UNREADABLE", "authority"),
            ("ledger", {"ledger_path": str(self.tmp / "absent_ledger.sqlite3")},
             "LEDGER_STORE_UNREADABLE", "ledger"),
        ):
            with self.subTest(label=label):
                result, exit_code, stdout = self.run_launcher_raw(
                    fx, output_name=f"missing_{label}.json", **overrides)
                _assert_complete_envelope_shape(self, result)
                _assert_not_production_pass(self, result, exit_code, stdout)
                self.assertEqual(result["status"], "RESULT_SCHEMA_INCOMPLETE")
                self.assertTrue(
                    any(f.startswith(prefix) for f in result["observation_completeness"]["failures"]),
                    result["observation_completeness"]["failures"],
                )
                proof = result["mutation_proof"]
                self.assertIsNone(proof[f"{absent}_before"])
                self.assertIsNone(proof[f"{absent}_after"])
                self.assertIsNone(proof[f"{absent}_unchanged"])
                present = "ledger" if absent == "authority" else "authority"
                self.assertIsNotNone(proof[f"{present}_before"])
                self.assertIsNotNone(proof[f"{present}_after"])
                self.assertTrue(proof[f"{present}_unchanged"])

    def test_c01_t17_candidate02_missing_file_fails_closed(self) -> None:
        """correction_01_theorem: T17 missing-file half (preserved)."""
        fx = self.build_ledger(include_expected_fill=True)
        result, exit_code, stdout = self.run_launcher_raw(
            fx, candidate_path=str(self.tmp / "absent.json"))
        _assert_complete_envelope_shape(self, result)
        _assert_not_production_pass(self, result, exit_code, stdout)
        self.assertIn("CANDIDATE02_FILE_MISSING", result["observation_completeness"]["failures"])

    # -- C02-T09 end-to-end ------------------------------------------------

    def test_c02_t09_nulling_any_mandatory_observation_blocks_completion(self) -> None:
        """Direct proof of the Marco BLOCK defect 4 theorem, both ways:
        (a) end to end, by nulling each named observation in an otherwise
        complete launcher result via the nonproduction fixture seam; and
        (b) purely, by nulling each one in the real complete result object
        the launcher just produced and asserting the final validator reports
        it. Presence in a happy path is not treated as evidence."""
        fx = self.build_ledger(include_expected_fill=True)
        complete, exit_code, _ = self.run_bound_fixture(fx)
        self.assertEqual(complete["observation_completeness"]["failures"], [])
        self.assertEqual(exit_code, 3)
        identity_path = str(self.tmp / "fixture_identity.json")
        validate = self.probe["validate_mandatory_observations"]

        for dotted in C02_T09_REQUIRED_MANDATORY_PATHS:
            with self.subTest(observation=dotted, proof="pure"):
                mutated = json.loads(json.dumps(complete))
                node = mutated
                parts = dotted.split(".")
                for part in parts[:-1]:
                    node = node[part]
                node[parts[-1]] = None
                self.assertIn(f"MISSING_REQUIRED_FIELD:{dotted}", validate(mutated))
                # ...and the untouched result reports no missing field at all.
                self.assertEqual(validate(complete), [])
            with self.subTest(observation=dotted, proof="end_to_end"):
                result, code, stdout = self.run_launcher_raw(
                    fx, output_name=f"dropped_{parts[-1]}.json",
                    identity_path=identity_path, null_observations=(dotted,),
                )
                _assert_complete_envelope_shape(self, result)
                _assert_not_production_pass(self, result, code, stdout)
                self.assertEqual(code, 1)
                self.assertEqual(result["status"], "RESULT_SCHEMA_INCOMPLETE")
                self.assertFalse(result["observation_completeness"]["complete"])
                self.assertIn(
                    f"MISSING_REQUIRED_FIELD:{dotted}",
                    result["observation_completeness"]["failures"],
                )

    # -- preserved CORRECTION_01 runtime theorems --------------------------

    def test_c01_t10_authority_ledger_tail_mismatch_fails_closed(self) -> None:
        """correction_01_theorem: T10 (preserved). Uses the codebase's own
        sanctioned fault_hook mechanism (append_batch calls
        fault_hook("before_authority_commit") strictly after the ledger-side
        commit) to simulate a crash between the two commits: the ledger
        legitimately advances while the authority anchor update is rolled
        back, producing a real LEDGER_AHEAD_OF_AUTHORITY state."""
        def crash_before_authority_commit(stage: str) -> None:
            if stage == "before_authority_commit":
                raise sqlite3.OperationalError("simulated crash between ledger commit and authority commit")

        with self.assertRaises(Exception):
            self.build_ledger(include_expected_fill=True, fault_hook=crash_before_authority_commit)

        ledger_path = self.tmp / "ledger.sqlite3"
        self.assertTrue(ledger_path.exists())
        candidate_path = self.tmp / "candidate.json"
        _write_synthetic_candidate(candidate_path, conflict_domain=self.conflict_domain)
        raw_sha256, semantic_sha256 = _candidate_identity(candidate_path)
        fx = {
            "authority_path": str(self.binding.authority_store_resolved_path),
            "ledger_path": str(ledger_path),
            "candidate_path": str(candidate_path),
            "raw_sha256": raw_sha256,
            "semantic_sha256": semantic_sha256,
        }
        result, exit_code, stdout = self.run_launcher_raw(fx)
        _assert_complete_envelope_shape(self, result)
        _assert_not_production_pass(self, result, exit_code, stdout)
        self.assertEqual(result["tail"]["authority_ledger_relation"], "LEDGER_AHEAD_OF_AUTHORITY")
        self.assertIn("AUTHORITY_LEDGER_RELATION_NOT_EQUAL", result["observation_completeness"]["failures"])
        self._assert_full_mutation_proof(result)

    def test_c01_t13_t14_duplicate_conflicting_fill_rejected_at_construction(self) -> None:
        """correction_01_theorem: T13/T14 (preserved). Both share one
        underlying primitive: `replay_projection`'s duplicate-fill check
        raises `LedgerError(DUPLICATE_FILL_CONFLICT)` the moment a second
        FILL_OBSERVED event for the same venue_fill_id carries different
        canonical content -- `append_batch` validates via `replay_projection`
        BEFORE the ledger transaction begins, so this state can never even be
        persisted. The exact rejecting primitive is proven directly here,
        since the read-only launcher could never observe a state that cannot
        be written in the first place."""
        fx = self.build_ledger(include_expected_fill=True, ledger_name="ledger_conflict.sqlite3")
        acquisition = lb.acquire_active_emergency_control_only_v1(
            self.binding, canonical_repository_root=str(REPO_ROOT), active_contract=fx["contract"],
            expected_ledger_path=fx["ledger_path"], clock=self.clock, uuid_factory=self.uuidf,
        )
        self.assertIsNotNone(acquisition.handle)
        handle = acquisition.handle
        conflicting_fill = lb.canonical_kalshi_fill_payload(
            fill_id=EXPECTED_FILL_ID, order_id="order-1",
            price=Decimal("0.9000"), quantity=Decimal("1.00"), fee=Decimal("0.017500"),
            additional_fields={
                "market": "KXAAAGASD-26SEP02-4.1200", "outcome_side": "YES",
                "authoritative_created_time_utc": "2026-09-01T23:34:44.000000Z",
            },
        )
        try:
            with self.assertRaises(el.LedgerError) as ctx:
                handle.record_fill_observation({
                    "canonical_venue_payload": conflicting_fill,
                    "canonical_venue_payload_sha256": hashlib.sha256(canonical_json_bytes(conflicting_fill)).hexdigest(),
                    "client_order_id": "client-order-1", "source_operation": "SYNTHETIC_FILL_READ",
                    "source_request_id": "req-fill-2", "venue_fill_id": EXPECTED_FILL_ID,
                    "venue_order_id": "order-1", "venue_payload_schema_id": "fill-v1",
                })
            self.assertEqual(ctx.exception.code, el.FailureCode.DUPLICATE_FILL_CONFLICT)
        finally:
            # The rejection happens inside replay_projection, strictly before
            # any DB transaction is opened -- the session and its connections
            # remain valid, so a normal close (which appends
            # RESTRICTED_SESSION_ENDED) is safe and required here to release
            # the SQLite exclusive lock before tearDown's cleanup runs.
            handle.close()

    def test_c01_t18_deterministic_read_failure_is_attempted_exactly_once(self) -> None:
        """correction_01_theorem: T18 runtime half (preserved). A
        deterministically unreadable store yields exactly one open attempt
        and a non-zero exit -- proven by counting the classification, which
        a retry loop would emit more than once."""
        fx = self.build_ledger(include_expected_fill=True)
        corrupt_ledger = self.tmp / "one_attempt_ledger.sqlite3"
        corrupt_ledger.write_bytes(b"deterministically unreadable")
        result, exit_code, stdout = self.run_launcher_raw(fx, ledger_path=str(corrupt_ledger))
        _assert_not_production_pass(self, result, exit_code, stdout)
        ledger_failures = [
            f for f in result["observation_completeness"]["failures"]
            if f.startswith("LEDGER_SCHEMA_OR_INTEGRITY_FAILED") or f.startswith("LEDGER_STORE_OPEN_FAILED")
        ]
        self.assertEqual(len(ledger_failures), 1, result["observation_completeness"]["failures"])

    def test_c01_t20_launcher_invocation_leaves_canonical_repository_untouched(self) -> None:
        """correction_01_theorem: T20 (preserved)."""
        before = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "status", "--porcelain=v1", "--untracked-files=all"],
            capture_output=True, text=True, check=True,
        ).stdout
        fx = self.build_ledger(include_expected_fill=True)
        self.run_launcher(fx)
        after = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "status", "--porcelain=v1", "--untracked-files=all"],
            capture_output=True, text=True, check=True,
        ).stdout
        self.assertEqual(before, after)

    # -- CORRECTION_03: atomic exclusive result creation, end to end -------

    @staticmethod
    def _fingerprint(path: Path) -> tuple:
        data = path.read_bytes()
        st = os.stat(path)
        return (data, hashlib.sha256(data).hexdigest(), st.st_size, st.st_mtime_ns)

    def _bound_identity(self, fx: dict) -> str:
        first, _ = self.run_launcher(fx, output_name="identity_probe_result.json")
        return self.bind_fixture_identity(first)

    def _assert_refused_existing_output(self, result: dict, exit_code: int, stdout: str) -> None:
        """Shared C03 failure theorem: path validation ACCEPTED the
        destination, and the exclusive create alone refused it -- with the
        otherwise complete bound fixture reporting that as its only failure."""
        _assert_complete_envelope_shape(self, result)
        _assert_not_production_pass(self, result, exit_code, stdout)
        self.assertEqual(exit_code, 1)
        self.assertEqual(result["status"], "RESULT_SCHEMA_INCOMPLETE")
        self.assertFalse(result["observation_completeness"]["complete"])
        self.assertTrue(result["output_sink"]["output_sink_safe"], "path layer must have accepted it")
        self.assertFalse(result["output_sink"]["output_written"])
        failures = result["observation_completeness"]["failures"]
        self.assertEqual(failures, ["OUTPUT_PATH_ALREADY_EXISTS"], failures)
        self.assertIn("READ_ONLY_REVALIDATION_TERMINAL=RESULT_SCHEMA_INCOMPLETE", stdout)
        self.assertIn("RESULT_WRITTEN=NONE", stdout)
        self.assertNotIn("RESULT_SHA256=", stdout)
        self.assertNotIn("RESULT_BYTES=", stdout)

    def test_c03_t01_real_hard_link_to_authority_or_ledger_is_never_modified(self) -> None:
        """Real NTFS hard links, OUTSIDE every protected root, whose file
        objects are the synthetic authority / ledger stores the launcher just
        read. Path normalization and link resolution cannot see the alias --
        `output_sink_safe` is true -- and the exclusive create is what stops
        the write."""
        fx = self.build_ledger(include_expected_fill=True)
        identity_path = self._bound_identity(fx)
        for label, target in (("authority", Path(fx["authority_path"])), ("ledger", Path(fx["ledger_path"]))):
            with self.subTest(store=label):
                outside = self.tmp / f"operator_output_{label}"
                outside.mkdir()
                link = outside / "result.json"
                os.link(target, link)
                self.assertTrue(os.path.samefile(target, link))
                self.assertEqual(os.stat(target).st_nlink, 2)
                before = self._fingerprint(target)
                result, exit_code, stdout = self.run_launcher_raw(
                    fx, output_name=None, output_path=str(link), identity_path=identity_path,
                )
                self._assert_refused_existing_output(result, exit_code, stdout)
                self.assertEqual(self._fingerprint(target), before, f"{label} store bytes/hash/size/mtime changed")
                self.assertEqual(self._fingerprint(link), before)
                self.assertTrue(os.path.samefile(target, link), "link must still refer to the original object")
                self.assertEqual(os.stat(target).st_nlink, 2)
                # The store the launcher read is still internally unchanged too.
                self.assertTrue(result["mutation_proof"][f"{label}_unchanged"])

    def test_c03_t02_ordinary_pre_existing_output_file_is_never_modified(self) -> None:
        fx = self.build_ledger(include_expected_fill=True)
        identity_path = self._bound_identity(fx)
        existing = self.tmp / "operator_output" / "result.json"
        existing.parent.mkdir()
        existing.write_bytes(b'{"an":"operator file that must survive"}\r\n\x00tail')
        before = self._fingerprint(existing)
        result, exit_code, stdout = self.run_launcher_raw(
            fx, output_name=None, output_path=str(existing), identity_path=identity_path,
        )
        self._assert_refused_existing_output(result, exit_code, stdout)
        self.assertEqual(self._fingerprint(existing), before)

    def test_c03_t03_t06_object_appearing_after_validation_is_refused_without_retry(self) -> None:
        """Deterministic validation-to-create race. The destination does not
        exist when `classify_output_sink` accepts it; the nonproduction hook
        then places an object there exactly as a racing process would, and
        the exclusive create must refuse it and leave it byte-for-byte intact.
        A retry that removed, renamed, or rewrote the object would change its
        bytes or report a second output classification."""
        fx = self.build_ledger(include_expected_fill=True)
        identity_path = self._bound_identity(fx)
        destination = self.tmp / "race_output" / "result.json"
        destination.parent.mkdir()
        self.assertFalse(destination.exists())
        result, exit_code, stdout = self.run_launcher_raw(
            fx, output_name=None, output_path=str(destination), identity_path=identity_path, race_occupy=True,
        )
        self._assert_refused_existing_output(result, exit_code, stdout)
        self.assertIn("race_occupy_output_before_create", result["mode"]["fixture_overrides"])
        self.assertEqual(destination.read_bytes(), self.probe["FIXTURE_RACE_OBJECT_BYTES"])
        output_classifications = [
            f for f in result["observation_completeness"]["failures"] if f.startswith("OUTPUT_")
        ]
        self.assertEqual(output_classifications, ["OUTPUT_PATH_ALREADY_EXISTS"])
        self.assertEqual(sorted(p.name for p in destination.parent.iterdir()), ["result.json"])

    def test_c03_t03_race_hook_is_refused_outside_fixture_mode(self) -> None:
        fx = self.build_ledger(include_expected_fill=True)
        destination = self.tmp / "race_refused" / "result.json"
        destination.parent.mkdir()
        proc = subprocess.run(
            [PWSH, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(LAUNCHER_PATH),
             "-Candidate02Path", fx["candidate_path"], "-OutputPath", str(destination),
             "-FixtureRaceOccupyOutputBeforeCreate"],
            capture_output=True, text=True, timeout=180,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertNotIn("READ_ONLY_REVALIDATION_TERMINAL=PASS", proc.stdout)
        result = next(json.loads(line.strip()) for line in proc.stdout.splitlines()
                      if line.strip().startswith("{") and '"schema"' in line)
        _assert_complete_envelope_shape(self, result)
        self.assertTrue(
            any(f.startswith("FIXTURE_OVERRIDE_WITHOUT_FIXTURE_MODE") for f in result["observation_completeness"]["failures"]),
            result["observation_completeness"]["failures"],
        )
        self.assertIsNone(result["mutation_proof"]["authority_before"])
        # The refused hook never ran, so the only object at the destination is
        # the refusal result itself -- never the race marker.
        if destination.exists():
            self.assertNotEqual(destination.read_bytes(), self.probe["FIXTURE_RACE_OBJECT_BYTES"])

    def test_c03_t04_genuinely_new_safe_output_receives_the_result(self) -> None:
        fx = self.build_ledger(include_expected_fill=True)
        identity_path = self._bound_identity(fx)
        destination = self.tmp / "fresh_operator_output" / "nested" / "result.json"
        destination.parent.mkdir(parents=True)
        self.assertFalse(destination.exists())
        result, exit_code, stdout = self.run_launcher_raw(
            fx, output_name=None, output_path=str(destination), identity_path=identity_path,
        )
        _assert_complete_envelope_shape(self, result)
        _assert_not_production_pass(self, result, exit_code, stdout)
        self.assertEqual(exit_code, 3)
        self.assertEqual(result["status"], "NONPRODUCTION_FIXTURE_COMPLETE")
        self.assertEqual(result["observation_completeness"]["failures"], [])
        self.assertTrue(result["output_sink"]["output_sink_safe"])
        self.assertTrue(result["output_sink"]["output_written"])
        self.assertTrue(destination.is_file())
        self.assertEqual(json.loads(destination.read_text(encoding="utf-8")), result)
        written = destination.read_bytes()
        self.assertIn(f"RESULT_BYTES={len(written)}", stdout)
        self.assertIn(f"RESULT_SHA256={hashlib.sha256(written).hexdigest()}", stdout)
        self.assertNotIn("RESULT_WRITTEN=NONE", stdout)


if __name__ == "__main__":
    unittest.main()
