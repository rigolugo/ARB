"""Generic repository-resident runner for the configurable read-only shadow
experiment (architecture R1-D07_SHADOW_EXPERIMENT_CONFIGURABLE_SELECTOR_01;
repository installation R1-D07_SHADOW_CONFIGURABLE_EXPERIMENT_INFRASTRUCTURE_CANONICALIZATION_01).

DEFAULT IS REFUSAL.  ``--execute-authorized-run`` is a generic TECHNICAL
ACKNOWLEDGEMENT ONLY.  It grants nothing and is never recorded as an
authorization: live authorization is external, user-controlled, and any
credential-bearing live execution is performed only by the user from the
user's own authorized local PowerShell session.

Three layers:
  1. code-enforced immutable safety (constants.py, transport.py, write_guard.py):
     Kalshi Demo origin only, GET only, zero automatic retries, no production,
     no writer/release/Gate-D, no deployed N1/ledger/authority state, no
     repository write, secret-free evidence;
  2. JSON experiment input (--config): selector knobs + shadow sweep values +
     run_id only; grants no capability; strictly validated with no defaults;
     the derived whole-run request ceiling must not exceed the immutable
     MAX_WHOLE_RUN_REQUESTS bound;
  3. CLI acknowledgement (--execute-authorized-run).

Repository residence: the repository root is this file's own directory.  No
static canonical commit / tree / parent is embedded; the runner observes and
records HEAD / HEAD^{tree} / sole parent, and live mode requires origin
rigolugo/ARB, branch main, a clean worktree and a committed self-surface whose
on-disk Git blobs equal HEAD.  Canonical dependencies are imported from the
same repository's src.  Whether a particular live run is authorized is decided
externally: a separately prepared, user-operated live package pins the exact
then-authorized canonical identities.  An external checkout is never used.
In both modes --output-dir must resolve (real path, Windows case-insensitive)
outside the repository; otherwise OUTPUT_DIR_INSIDE_REPOSITORY fails closed
before credential presence inspection and before any output is created.

Modes:
  live    : --config FILE --output-dir NEW_DIR --execute-authorized-run
            config validation -> preflight -> one selector run -> four snapshot
            GETs -> offline sweep -> evidence
  replay  : --config FILE --output-dir NEW_DIR --replay-snapshot FILE
            offline sweep only (no network, no credentials)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parent
SHADOW_PACKAGE_PARENT = REPOSITORY_ROOT / "src" / "arb" / "venues" / "kalshi"
PACKAGE_ROOT = SHADOW_PACKAGE_PARENT / "shadow_experiment"
for _path in (SHADOW_PACKAGE_PARENT, REPOSITORY_ROOT / "src"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from shadow_experiment import constants as C  # noqa: E402
from shadow_experiment.canonical_binding import (  # noqa: E402
    PreconditionFailed, PreflightReport, bind_canonical_modules, verify_credential_presence, verify_interpreter,
    verify_repository_provenance)
from shadow_experiment.config import (  # noqa: E402
    ConfigError, b1_selection_mode, effective_config_document, load_config_bytes, selector_max_requests,
    snapshot_request_count, whole_run_request_ceiling)
from shadow_experiment.write_guard import scan_package, scan_source  # noqa: E402

EXIT_DONE = 0
EXIT_REFUSED = 2
EXIT_PRECONDITION_FAILED = 3
EXIT_EVIDENCE_INTEGRITY_FAILED = 4
EXIT_CONFIG_INVALID = 5


def _dump(obj) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")


def _emit(obj) -> None:
    print(json.dumps(obj, sort_keys=True, default=str))


def _acknowledgement_state(present: bool) -> dict:
    return {"flag": C.EXECUTION_ACKNOWLEDGEMENT_FLAG,
            "acknowledgement_present": present,
            "semantics": C.EXECUTION_ACKNOWLEDGEMENT_SEMANTICS,
            "live_authorization": C.EXTERNAL_AUTHORIZATION_STATEMENT}


def _capability_text(*, mode: str, network: bool, credentials_used: bool) -> str:
    return "\n".join([
        "CAPABILITY ACTIVITY",
        f"package_id = {C.PACKAGE_ID}",
        f"run_mode = {mode}",
        f"kalshi_demo_read_network = {'USED (GET only)' if network else 'NONE'}",
        "kalshi_demo_writes = 0 ; CREATE = 0 ; CANCEL = 0 ; POST/PUT/PATCH/DELETE = 0",
        "gate_d = NONE ; release_only = NONE ; normal_writer = NONE ; writer permits = NONE",
        "production = NONE",
        f"credential use = {'canonical selector EnvironmentRsaSigner (path-based key) for signed GETs' if credentials_used else 'NONE'}",
        "credential values inspected/printed/exported/serialized = NONE",
        "temporary PEM bridge = NOT USED",
        "persistent/deployed N1 state = NONE ; ledger/authority opened = NONE",
        "repository writes = NONE ; package installation = NONE",
        f"automatic_retries = {C.AUTOMATIC_RETRIES}",
        f"json config authority = {C.CONFIG_AUTHORITY}",
        f"execute-authorized-run flag = {C.EXECUTION_ACKNOWLEDGEMENT_SEMANTICS}",
        f"selection authority = {C.SHADOW_ONLY_AUTHORITY}",
        "",
    ])


def scan_shadow_surface() -> list:
    """Static write guard over the root runner plus the installed shadow package
    only.  The rest of ARB intentionally contains write-capable code and is
    never scanned or imported as part of this surface."""
    runner = Path(__file__).resolve()
    return (scan_source(runner.read_text(encoding="utf-8"), C.RUNNER_RELATIVE_PATH)
            + scan_package(PACKAGE_ROOT))


def _write_evidence(out: Path, files: dict) -> dict:
    manifest = {}
    for name, data in files.items():
        (out / name).write_bytes(data)
        manifest[name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    for name, meta in manifest.items():  # re-read verification
        data = (out / name).read_bytes()
        if len(data) != meta["bytes"] or hashlib.sha256(data).hexdigest() != meta["sha256"]:
            raise RuntimeError("EVIDENCE_INTEGRITY_FAILED")
    m = _dump({"package_id": C.PACKAGE_ID, "files": manifest})
    (out / "EVIDENCE_MANIFEST.json").write_bytes(m)
    if (out / "EVIDENCE_MANIFEST.json").read_bytes() != m:
        raise RuntimeError("EVIDENCE_INTEGRITY_FAILED")
    return manifest


OUTPUT_DIR_INSIDE_REPOSITORY = "OUTPUT_DIR_INSIDE_REPOSITORY"


def _resolved_path_for_containment(path: Path) -> Path:
    """Filesystem-aware resolution: existing components (including symlink /
    junction / reparse-point parents) are resolved to their real targets."""
    return Path(path).resolve(strict=False)


def _is_equal_or_descendant(candidate: Path, root: Path) -> bool:
    """True iff ``candidate`` equals ``root`` or lies beneath it.  Not lexical
    ``startswith``: component-wise ``commonpath`` over ``normcase`` forms
    (case-insensitive on Windows).  Different drives / root namespaces raise in
    ``commonpath`` and are never containment."""
    c = os.path.normcase(str(candidate))
    r = os.path.normcase(str(root))
    try:
        return os.path.commonpath([c, r]) == r
    except ValueError:
        return False


def _validate_output_target(out_dir: Path, repo_root: Path, report: PreflightReport) -> None:
    """Fail closed if the resolved output target is the repository root or any
    path beneath it.  Non-mutating; no bypass.  The failure label is fixed and
    contains no path."""
    repo_real = Path(repo_root).resolve(strict=True)
    target_real = _resolved_path_for_containment(Path(out_dir))
    if _is_equal_or_descendant(target_real, repo_real):
        report.checks.append({"check": "output_dir_outside_repository", "result": "FAIL",
                              "observed": OUTPUT_DIR_INSIDE_REPOSITORY})
        raise PreconditionFailed("PRECONDITION_FAILED", OUTPUT_DIR_INSIDE_REPOSITORY)
    report.add("output_dir_outside_repository", True, "PASS")


def _new_output_dir(path: Path) -> Path:
    if path.exists():
        raise PreconditionFailed("PRECONDITION_FAILED", "output directory already exists")
    path.mkdir(parents=True)
    return path


def _load_replay_snapshot(path: Path) -> dict:
    from shadow_experiment.live_capture import SNAPSHOT_SCHEMA
    try:
        raw = path.read_bytes()
        doc = json.loads(raw.decode("utf-8"), parse_constant=lambda t: (_ for _ in ()).throw(ValueError(t)))
    except (OSError, UnicodeDecodeError, ValueError):
        raise PreconditionFailed("PRECONDITION_FAILED", "replay snapshot unreadable or malformed") from None
    if type(doc) is not dict or doc.get("schema") != SNAPSHOT_SCHEMA:
        raise PreconditionFailed("PRECONDITION_FAILED", "replay snapshot schema mismatch")
    return doc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="run_shadow_experiment.py", allow_abbrev=False)
    parser.add_argument("--config", default=None)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--replay-snapshot", default=None)
    parser.add_argument(C.EXECUTION_ACKNOWLEDGEMENT_FLAG, dest="acknowledged", action="store_true")
    return parser


def run(argv=None, *, env=None, select_fn=None, transport_factory=None, signer_factory=None,
        interpreter_check=True, now_utc=None) -> int:
    args = _build_parser().parse_args(argv)
    env = os.environ if env is None else env
    replay = args.replay_snapshot is not None

    # ---- layer 3: CLI acknowledgement (refusal before anything else) --------
    if replay and args.acknowledged:
        _emit({"status": "REFUSED", "reason": "MODE_AMBIGUOUS: --replay-snapshot is offline-only and must not "
               "be combined with " + C.EXECUTION_ACKNOWLEDGEMENT_FLAG})
        return EXIT_REFUSED
    if not replay and not args.acknowledged:
        # default refusal: no config read, no preflight, no env, no network
        _emit({"status": "REFUSED", "reason": "execution acknowledgement flag absent",
               "required_flag": C.EXECUTION_ACKNOWLEDGEMENT_FLAG,
               "flag_semantics": C.EXECUTION_ACKNOWLEDGEMENT_SEMANTICS})
        return EXIT_REFUSED
    if args.config is None:
        _emit({"status": "REFUSED", "reason": "CONFIG_REQUIRED: --config is required; there is no default config"})
        return EXIT_REFUSED
    if args.output_dir is None:
        _emit({"status": "REFUSED", "reason": "OUTPUT_DIR_REQUIRED: --output-dir is required"})
        return EXIT_REFUSED

    # ---- layer 2: exact config bytes -> strict validation -------------------
    try:
        config_bytes = Path(args.config).read_bytes()
    except OSError:
        _emit({"status": "CONFIG_INVALID", "error": {"code": "CONFIG_UNREADABLE", "path": "$", "detail": ""}})
        return EXIT_CONFIG_INVALID
    try:
        cfg = load_config_bytes(config_bytes)
    except ConfigError as exc:
        _emit({"status": "CONFIG_INVALID", "error": exc.to_dict()})
        return EXIT_CONFIG_INVALID
    config_sha256 = hashlib.sha256(config_bytes).hexdigest()
    effective_doc = effective_config_document(cfg)
    effective_bytes = _dump(effective_doc)
    request_ceiling = whole_run_request_ceiling(cfg)
    accounting_plan = {"selector_max_requests": selector_max_requests(cfg),
                       "snapshot_request_count": snapshot_request_count(),
                       "whole_run_request_ceiling": request_ceiling}

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.output_dir)
    mode = "REPLAY" if replay else "LIVE"

    # ---- layer 1: preflight -------------------------------------------------
    report = PreflightReport()
    try:
        report.add("config_validated", True, {"sha256": config_sha256, "bytes": len(config_bytes)})
        report.add("request_ceiling_derived_from_config",
                   type(request_ceiling) is int and 0 < request_ceiling <= C.MAX_WHOLE_RUN_REQUESTS,
                   {**accounting_plan, "max_whole_run_requests": C.MAX_WHOLE_RUN_REQUESTS})
        if interpreter_check:
            verify_interpreter(report)
        provenance = verify_repository_provenance(REPOSITORY_ROOT, report, live=not replay)
        problems = scan_shadow_surface()
        report.add("static_write_path_guard", not problems, problems or "PASS")
        snapshot_doc = None
        if replay:
            snapshot_doc = _load_replay_snapshot(Path(args.replay_snapshot))
            report.add("replay_snapshot_schema", True, snapshot_doc.get("schema"))
        # non-mutating output containment, both modes, before credentials and before any output write
        _validate_output_target(out_dir, REPOSITORY_ROOT, report)
        if not replay:
            verify_credential_presence(report, env)
        out = _new_output_dir(out_dir)
        report.add("output_dir_new", True, str(out))
        mods = bind_canonical_modules(REPOSITORY_ROOT)
        report.add("canonical_modules_bound_from_repo_src", True, sorted(m.__name__ for m in mods.values()))
    except PreconditionFailed as exc:
        _emit({"status": "PRECONDITION_FAILED", "failed_check": exc.detail, "checks": report.checks})
        return EXIT_PRECONDITION_FAILED

    from shadow_experiment import live_capture, sweep  # noqa: E402
    from shadow_experiment.shadow_evaluator import evaluator_identity  # noqa: E402

    run_manifest = {
        "package_id": C.PACKAGE_ID, "run_id": cfg.run_id, "mode": mode,
        "canonicalization_task_id": C.CANONICALIZATION_TASK_ID,
        "repository_provenance": provenance,
        "config": {"filename_as_supplied": args.config, "bytes": len(config_bytes), "sha256": config_sha256,
                   "input_copy": "SELECTOR_CONFIG_INPUT.json", "effective_copy": "SELECTOR_CONFIG_EFFECTIVE.json",
                   "effective_sha256": hashlib.sha256(effective_bytes).hexdigest(),
                   "authority": C.CONFIG_AUTHORITY},
        "request_accounting_plan": accounting_plan,
        "max_whole_run_requests": C.MAX_WHOLE_RUN_REQUESTS,
        "cli_acknowledgement": _acknowledgement_state(args.acknowledged),
        "b1_selection_mode": b1_selection_mode(cfg),
        "selection_authority": C.SHADOW_ONLY_AUTHORITY,
        "trial_G": cfg.shadow_experiment.trial_g, "trial_G_authority": C.TRIAL_G_AUTHORITY,
        "canonical_G_selection": C.CANONICAL_G_SELECTION,
        "minimum_spread_matrix": [format(s, "f") for s in cfg.shadow_experiment.minimum_spread_usd],
        "selected_market_count_max": C.SELECTED_MARKET_COUNT_MAX,
        "automatic_retries": C.AUTOMATIC_RETRIES, "evaluator": evaluator_identity(),
        "preflight": report.checks, "started_utc": stamp,
    }
    files = {"SELECTOR_CONFIG_INPUT.json": config_bytes, "SELECTOR_CONFIG_EFFECTIVE.json": effective_bytes}
    if replay:
        matrix = sweep.run_sweep(mods, cfg, snapshot_doc)
        terminal = {"terminal_classification": matrix["terminal"], "network": "NONE"}
        files["LIVE_READ_SNAPSHOT_SANITIZED.json"] = _dump(snapshot_doc)
        files["SELECTOR_DIAGNOSTICS.json"] = _dump({
            "schema": "ShadowSelectorDiagnosticsV1", "mode": "REPLAY", "selector_invoked": False,
            "reason": "REPLAY_MODE_SELECTOR_NOT_INVOKED"})
        capability = _capability_text(mode=mode, network=False, credentials_used=False)
        accounting = {**accounting_plan, "requests": [], "request_count": 0, "demo_write_count": 0,
                      "automatic_retries": 0}
    else:
        sel = mods["selector"]
        if transport_factory is None:
            from shadow_experiment.transport import AccountedDemoTransport
            transport = AccountedDemoTransport(sel, request_ceiling=request_ceiling)
        else:
            transport = transport_factory(sel, request_ceiling)
        signer = (signer_factory or (lambda s: s.EnvironmentRsaSigner()))(sel)
        kwargs = {"select_fn": select_fn}
        if now_utc is not None:
            kwargs["now_utc"] = now_utc
        captured = live_capture.run_live_capture(mods, cfg, transport, signer, **kwargs)
        files["SELECTOR_RESULT.json"] = _dump({
            "selector_invocations": captured["selector_invocations"], "result": captured["selector_result"],
            "b1_selection_mode": b1_selection_mode(cfg), "selection_authority": C.SHADOW_ONLY_AUTHORITY})
        files["SELECTOR_DIAGNOSTICS.json"] = _dump(captured["selector_diagnostics"])
        accounting = {**accounting_plan, "requests": transport.records, "request_count": len(transport.records),
                      "by_phase": {}, "methods": sorted({r["method"] for r in transport.records}),
                      "demo_write_count": 0, "automatic_retries": 0}
        for r in transport.records:
            accounting["by_phase"][r["phase"]] = accounting["by_phase"].get(r["phase"], 0) + 1
        capability = _capability_text(mode=mode, network=True, credentials_used=True)
        if captured["snapshot"] is None:
            matrix = None
            terminal = {"terminal_classification": captured["terminal"],
                        "detail": captured.get("terminal_detail")}
            if captured["selector_result"].get("status") == "HALTED":
                terminal["selector_halt"] = {k: captured["selector_result"].get(k) for k in ("code", "phase", "detail")}
        else:
            snap_bytes = _dump(captured["snapshot"])
            files["LIVE_READ_SNAPSHOT_SANITIZED.json"] = snap_bytes
            matrix = sweep.run_sweep(mods, cfg, json.loads(snap_bytes))   # sweep only from serialized snapshot
            terminal = {"terminal_classification": matrix["terminal"]}
    files["READ_REQUEST_ACCOUNTING.json"] = _dump(accounting)
    if matrix is not None:
        files["SHADOW_MATRIX.json"] = _dump(matrix)
        files["SHADOW_MATRIX.csv"] = sweep.matrix_csv(matrix).encode("utf-8")
    terminal.update({"package_id": C.PACKAGE_ID, "run_id": cfg.run_id, "mode": mode, "automatic_retries": 0,
                     "demo_writes": 0, "production": "NONE", "no_profitability_claim": True,
                     "selection_authority": C.SHADOW_ONLY_AUTHORITY,
                     "config_sha256": config_sha256, "whole_run_request_ceiling": request_ceiling})
    files["TERMINAL_RESULT.json"] = _dump(terminal)
    files["CAPABILITY_ACTIVITY.txt"] = capability.encode("utf-8")
    run_manifest["finished_utc"] = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    files["RUN_MANIFEST.json"] = _dump(run_manifest)
    try:
        _write_evidence(out, files)
    except RuntimeError:
        _emit({"status": "EVIDENCE_INTEGRITY_FAILED"})
        return EXIT_EVIDENCE_INTEGRITY_FAILED
    _emit({"status": "DONE", "run_id": cfg.run_id, "mode": mode,
           "terminal": terminal["terminal_classification"], "output_dir": str(out)})
    return EXIT_DONE


if __name__ == "__main__":
    raise SystemExit(run())
