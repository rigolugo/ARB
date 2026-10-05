"""In-repository provenance verification and exact-path canonical imports.

Every check here is local (git subprocess on the runner's own repository
checkout, file hashing, interpreter/environment inspection).  No network, no
credential value read: credential environment variables are tested for
presence/absence only and their values are never returned or serialized.

There is deliberately no static canonical commit / tree / parent pin.  The
repository root is resolved from the root runner's own location; the current
``HEAD``, ``HEAD^{tree}`` and sole parent are OBSERVED and recorded.  Live
mode additionally requires canonical origin, branch ``main``, a clean
worktree, and a tracked/committed self-surface whose on-disk Git blobs equal
the ``HEAD:<path>`` blobs.  An external checkout is never substituted.
"""

from __future__ import annotations

import hashlib
import importlib
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping

from . import constants as C


class PreconditionFailed(RuntimeError):
    """Fail-closed precondition failure.  ``code`` is a fixed secret-free label."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code if not detail else f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass
class PreflightReport:
    checks: list = field(default_factory=list)

    def add(self, name: str, ok: bool, observed: object) -> None:
        self.checks.append({"check": name, "result": "PASS" if ok else "FAIL", "observed": observed})
        if not ok:
            raise PreconditionFailed("PRECONDITION_FAILED", name)


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=False)
    if out.returncode != 0:
        raise PreconditionFailed("PRECONDITION_FAILED", "git " + " ".join(args[:2]))
    return out.stdout.decode("utf-8").strip()


def _blob_id(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\x00" % len(data) + data).hexdigest()


def self_surface_paths(repo: Path) -> list:
    """Repository-relative paths of the root runner and every package module on disk."""
    repo = Path(repo)
    package = repo / C.PACKAGE_RELATIVE_DIR
    modules = sorted(p.relative_to(repo).as_posix() for p in package.glob("*.py"))
    return [C.RUNNER_RELATIVE_PATH, *modules]


def _blob_pair(repo: Path, rel: str, git: Callable) -> dict:
    on_disk = _blob_id((Path(repo) / rel).read_bytes())
    try:
        committed = git(repo, "rev-parse", f"HEAD:{rel}")
    except PreconditionFailed:
        committed = None
    return {"on_disk": on_disk, "committed": committed}


def verify_repository_provenance(repo: Path, report: PreflightReport, *, live: bool,
                                 git: Callable = _git) -> dict:
    """Observe and record in-repository provenance.

    Both modes record origin, branch, cleanliness, ``HEAD``, ``HEAD^{tree}``,
    parents, and the self-surface / dependency Git blobs (on disk vs ``HEAD``).
    Live mode fails closed unless: origin is ``rigolugo/ARB``; branch is
    ``main``; the worktree is clean; ``HEAD`` has exactly one parent; the
    committed package module set equals the on-disk set; and every self-surface
    and dependency file's on-disk blob equals its ``HEAD:<path>`` blob.
    Replay mode (offline) records the same facts without requiring them.
    """
    repo = Path(repo)
    mode = "LIVE" if live else "REPLAY"
    report.add("repo_path_exists", (repo / ".git").exists(), str(repo))
    origin = git(repo, "remote", "get-url", "origin")
    head = git(repo, "rev-parse", "HEAD")
    tree = git(repo, "rev-parse", "HEAD^{tree}")
    parents = git(repo, "rev-list", "--parents", "-n", "1", "HEAD").split()[1:]
    try:
        branch = git(repo, "symbolic-ref", "--short", "HEAD")
    except PreconditionFailed:
        branch = None
    status = git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    surface = self_surface_paths(repo)
    committed_listing = git(repo, "ls-tree", "--name-only", "HEAD", C.PACKAGE_RELATIVE_DIR + "/")
    committed_modules = sorted(p for p in committed_listing.splitlines() if p.endswith(".py"))
    surface_blobs = {rel: _blob_pair(repo, rel, git) for rel in surface}
    dependency_blobs = {rel: _blob_pair(repo, rel, git) for rel in C.DEPENDENCY_RELATIVE_PATHS}
    provenance = {
        "policy": C.PROVENANCE_POLICY,
        "live_authorization_pin": C.LIVE_AUTHORIZATION_PIN,
        "mode": mode,
        "repository_root": str(repo),
        "origin": origin,
        "branch": branch,
        "worktree_clean": status == "",
        "head": head,
        "tree": tree,
        "parents": parents,
        "self_surface_blobs": surface_blobs,
        "dependency_blobs": dependency_blobs,
    }
    if live:
        report.add("origin_is_rigolugo_ARB", origin in C.CANONICAL_ORIGIN_URLS, origin)
        report.add("branch_is_main", branch == C.LIVE_REQUIRED_BRANCH, branch)
        report.add("worktree_clean", status == "", "clean" if status == "" else "DIRTY")
        report.add("head_has_sole_parent", len(parents) == 1,
                   {"head": head, "tree": tree, "parents": parents})
        report.add("self_surface_module_set_committed", committed_modules == surface[1:],
                   {"on_disk": surface[1:], "committed": committed_modules})
        for rel, pair in surface_blobs.items():
            report.add(f"self_surface_blob:{rel}", pair["committed"] is not None and pair["on_disk"] == pair["committed"],
                       pair)
        for rel, pair in dependency_blobs.items():
            report.add(f"dependency_blob:{rel}", pair["committed"] is not None and pair["on_disk"] == pair["committed"],
                       pair)
    else:
        report.add("repository_provenance_recorded", True,
                   {"head": head, "tree": tree, "parents": parents, "branch": branch,
                    "worktree_clean": status == ""})
    return provenance


def verify_interpreter(report: PreflightReport, *, executable: str | None = None, version=None) -> None:
    exe = os.path.normcase(os.path.abspath(executable or sys.executable))
    expected = os.path.normcase(os.path.abspath(C.EXPECTED_PYTHON_EXECUTABLE))
    report.add("python_executable", exe == expected, executable or sys.executable)
    ver = tuple((version or sys.version_info)[:2])
    report.add("python_version_3_12", ver == C.EXPECTED_PYTHON_MAJOR_MINOR, ".".join(map(str, ver)))


def verify_credential_presence(report: PreflightReport, env: Mapping[str, str] | None = None) -> None:
    """Presence only.  Values are never returned, logged or serialized."""
    env = os.environ if env is None else env
    report.add("api_key_id_present", bool(env.get(C.API_KEY_ID_ENV)), "PRESENT" if env.get(C.API_KEY_ID_ENV) else "ABSENT")
    report.add("private_key_path_present", bool(env.get(C.PRIVATE_KEY_PATH_ENV)),
               "PRESENT" if env.get(C.PRIVATE_KEY_PATH_ENV) else "ABSENT")
    report.add("legacy_private_key_pem_absent", C.LEGACY_PRIVATE_KEY_PEM_ENV not in env,
               "ABSENT" if C.LEGACY_PRIVATE_KEY_PEM_ENV not in env else "PRESENT")


def bind_canonical_modules(repo: Path) -> dict:
    """Import the canonical modules from ``<repo>/src`` and prove each
    resolved file lives under that exact directory."""
    src = (Path(repo) / "src").resolve()
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    names = {
        "selector": "arb.venues.kalshi.d07_market_selector",
        "mm": "arb.venues.kalshi.minimal_market_maker",
        "risk": "arb.venues.kalshi.risk_control",
        "runner": "arb.venues.kalshi.minimal_market_maker_experiment_runner",
    }
    modules = {}
    for key, name in names.items():
        module = importlib.import_module(name)
        path = Path(module.__file__).resolve()
        if src not in path.parents:
            raise PreconditionFailed("PRECONDITION_FAILED", f"canonical import path mismatch: {name}")
        modules[key] = module
    return modules
