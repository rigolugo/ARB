"""Static write-surface guard over this package's own source (AST scan).

Fails if any package module (tests excluded):
* contains an HTTP write verb as a string constant;
* calls ``.request(...)`` with a first argument other than the literal GET;
* names a canonical write / writer / release / ledger / Gate-D symbol;
* names any identifier that looks like an order CREATE / CANCEL / amend /
  decrease surface;
* touches a canonical ``RunnerOperation`` member that is not a ``GET_*`` read;
* imports sqlite3, an HTTP client library other than the stdlib transport,
  or a canonical write module.
Forbidden tokens are assembled at runtime so this file does not trip itself.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_VERBS = {"PO" + "ST", "PU" + "T", "PAT" + "CH", "DEL" + "ETE"}
_FORBIDDEN_NAMES = {n.replace("~", "") for n in (
    "_DemoNormal~WriteTransport", "NormalWrite~Adapter", "issue_and_persist~_write_permit",
    "WriterEligibility~Gate", "run_gate_d~_ordinary_decision_loop", "Locked~Ledger",
    "EmergencyCancel~Gate", "_demo_path_to_pem~_credential_bridge", "acquire_active~_emergency_control_only_v1",
    "initialize_authority~_namespace", "evaluate_market_maker~_input", "Quote~PlanV1",
    "run_release~_orchestration_v1", "CREATE_ORDER~_V2", "CANCEL_ORDER~_V2",
)}
_ORDER_WRITE_IDENTIFIER = re.compile("(?i)(cre" + "ate|can" + "cel|am" + "end|decr" + "ease)_?orders?")
_FORBIDDEN_IMPORTS = {"sq" + "lite3", "requests", "urllib.request", "arb.execution_ledger",
                      "arb.venues.kalshi.ledger_binding", "arb.venues.kalshi.emergency_cancel"}
_RUNNER_OPERATION = "Runner" + "Operation"


def _identifier_problem(name: str):
    if name in _FORBIDDEN_NAMES:
        return "forbidden name"
    if _ORDER_WRITE_IDENTIFIER.search(name):
        return "order-write identifier"
    return None


def scan_source(text: str, filename: str = "<src>") -> list:
    problems = []
    tree = ast.parse(text, filename=filename)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.upper() in _VERBS:
            problems.append(f"{filename}:{node.lineno}: write verb constant {node.value!r}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "request":
            first = node.args[0] if node.args else None
            if not (isinstance(first, ast.Constant) and first.value == "GET"):
                problems.append(f"{filename}:{node.lineno}: .request() not literal GET")
        if isinstance(node, ast.Name):
            why = _identifier_problem(node.id)
            if why:
                problems.append(f"{filename}:{node.lineno}: {why} {node.id}")
        if isinstance(node, ast.Attribute):
            why = _identifier_problem(node.attr)
            if why:
                problems.append(f"{filename}:{node.lineno}: {why} attribute {node.attr}")
            owner = node.value
            owner_name = owner.attr if isinstance(owner, ast.Attribute) else (
                owner.id if isinstance(owner, ast.Name) else "")
            if owner_name == _RUNNER_OPERATION and not node.attr.startswith("GET_"):
                problems.append(f"{filename}:{node.lineno}: non-GET runner operation {node.attr}")
        if isinstance(node, ast.FunctionDef):
            why = _identifier_problem(node.name)
            if why:
                problems.append(f"{filename}:{node.lineno}: {why} function {node.name}")
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            names = [a.name for a in node.names]
            for m in mods:
                if m in _FORBIDDEN_IMPORTS or any(m.startswith(f + ".") for f in _FORBIDDEN_IMPORTS):
                    problems.append(f"{filename}:{node.lineno}: forbidden import {m}")
            for n in names:
                why = _identifier_problem(n)
                if why:
                    problems.append(f"{filename}:{node.lineno}: {why} imported {n}")
    return problems


def scan_package(package_root: Path) -> list:
    problems = []
    for path in sorted(Path(package_root).rglob("*.py")):
        if "tests" in path.parts:
            continue
        problems += scan_source(path.read_text(encoding="utf-8"), str(path.relative_to(package_root)))
    return problems
