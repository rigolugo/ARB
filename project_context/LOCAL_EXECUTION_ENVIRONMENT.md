# LOCAL_EXECUTION_ENVIRONMENT

## Purpose

This file records the default local execution environment and command-formatting conventions for the ARB project.

It is an operational convenience record only.

It does **not** grant network access, venue access, credential use, package installation, code changes, test execution, repository writes, Git commits, funding, orders, cancellations, trading, or any other capability. Every activity still requires the exact authorization applicable to that task.

If this file conflicts with `project_context/GUARDRAILS.md`, an exact active Gustavo authorization, or another higher-authority canonical control, the more restrictive higher-authority rule controls.

## 1. Default host environment

Unless Gustavo states otherwise for a specific task, assume the user-operated local environment is:

- operating system: Microsoft Windows;
- primary project shell: Windows PowerShell / PowerShell;
- Python environment manager: Miniconda / Conda;
- default active Conda environment for this project: `pmresearch`;
- Python major/minor target: CPython 3.12;
- currently observed local Python version: CPython 3.12.13.

Do not hard-bind future work to patch version `3.12.13` unless a task or accepted specification requires that exact patch version.

Before a task materially depends on interpreter identity, verify it from PowerShell:

```powershell
Get-Command python
python --version
python -c "import sys; print(sys.executable)"
```

When the intended Conda environment is already active, prefer:

```powershell
python ...
```

Do not replace it with the Windows `py` launcher unless a task explicitly requires the launcher.

### 1.1 Codex-specific Python and Windows sandbox policy

This subsection applies to Codex only. It does not replace the generic user command conventions in this document and does not bind Claude, whose interpreter, temp roots, artifact roots, and sandbox environment are configured and resolved independently.

Codex local configuration variables are:

```text
Codex local interpreter variable = ARB_CODEX_PYTHON_EXE
Codex temp-root variable = ARB_CODEX_TEMP_ROOT
Codex final-artifact variable = ARB_CODEX_ARTIFACT_ROOT
```

For ARB Python processes, Codex must use the interpreter identified by:

```powershell
$env:ARB_CODEX_PYTHON_EXE
```

Bare `python` may resolve to the Microsoft Store alias and is informational only for Codex. Before material Codex Python execution, verify the variable, Python version, `sys.executable`, and `tempfile.gettempdir()` using the interpreter-qualified commands in root `AGENTS.md`.

An unset, missing, non-executable, or wrong-environment variable is a stop condition. Codex must not silently fall back to `python`, `py`, a bundled interpreter, or another Conda environment.

Codex Python test processes preserve `TEMP`, `TMP`, and `ARB_CODEX_TEMP_ROOT`. Unless the active task explicitly supplies another Codex task-local root, Codex verifies:

```text
TEMP == TMP == ARB_CODEX_TEMP_ROOT
```

before testing. These values are Codex-local configuration, not shared Claude requirements.

The current no-admin Codex Windows sandbox is `unelevated`. Before any authorized Python test suite, Codex must run the nested-temp environment probe defined in root `AGENTS.md`: create and write a child file under a new `tempfile.mkdtemp()` root, rename and delete it, create and remove a nested directory, and remove the probe root with `shutil.rmtree()`.

The confirmed fallback condition is narrow: the temp root resolves correctly, `tempfile.mkdtemp()` succeeds, and a descendant mutation or recursive cleanup then fails with `PermissionError`, errno 13, and/or WinError 5 under the `unelevated` filesystem sandbox. Only when the active task already authorizes the exact offline Python test process may Codex run that process outside the filesystem sandbox as the same unelevated Windows user. All active-task capability limits remain unchanged, including network, credentials, venue access, writable repository paths, and persistent-state access. A network-prohibited task remains offline.

This fallback is process-bounded to the already-authorized Python test command and necessary cleanup of exact task-created temp material. It is not an unrestricted shell and does not permit administrator rights, an elevated sandbox workaround, global sandbox disable, repository or host ACL weakening, ownership changes, or deletion of unrelated temp material. Wrong interpreter/temp configuration and unrelated syntax, import, dependency, assertion, permission, filesystem, network, or credential failures remain hard stops.

After tests, Codex removes owned probe/test temp material, uses the same narrowly bounded outside-sandbox cleanup only when the exact known WinError-5 condition blocks cleanup, and verifies final repository cleanliness with:

```powershell
git status --porcelain
```

Final review artifacts are delivered under the task-resolved `$env:ARB_CODEX_ARTIFACT_ROOT`; no Codex-local absolute temp or artifact path is a shared Claude requirement.

### 1.2 Machine-local execution configuration (`LocalExecutionConfigV1`)

This subsection is shared/generic. It records the machine-local, non-secret execution configuration contract defined by `ARB_LOCAL_EXECUTION_CONFIG_V1_PORTABILITY_SPEC_01_CORRECTION_01`. Like the rest of this file, it describes how a local executable path is selected, not whether any activity is authorized.

#### 1.2.1 Schema and minimal shape

The schema identifier is exactly:

```text
ARB_LOCAL_EXECUTION_CONFIG_V1
```

A V1 config producer emits this minimal semantic shape:

```json
{
  "schema": "ARB_LOCAL_EXECUTION_CONFIG_V1",
  "python": {
    "executable": "C:\\absolute\\path\\to\\python.exe"
  }
}
```

The V1 normative fields are exactly `schema`, `python`, and `python.executable`. No other V1 field is defined; a consumer must not infer capability, security authority, risk state, repository identity, or fallback behavior from any unrecognized field. Adding a normative field requires a later schema/specification change.

- `schema` must be a JSON string exactly equal to `ARB_LOCAL_EXECUTION_CONFIG_V1`.
- `python` must be a JSON object.
- `python.executable` must be a non-empty JSON string naming an absolute local filesystem path to the intended Python executable; the path must exist as a file before it is selected. No executable-name suffix is proof of validity.

V1 carries no economic value; floating-point, precision, and monetary-rounding semantics do not apply.

#### 1.2.2 Default location, non-secret boundary, and repository exclusion

The default Windows config location is exactly:

```text
%LOCALAPPDATA%\ARB\arb-local-config.json
```

The file is machine-local operational state and lives outside the canonical repository. The default config file, any explicitly selected config file, and any machine-local sample instantiated from this contract must not be committed to `rigolugo/ARB` merely because the schema exists.

`LocalExecutionConfigV1` is for non-secret machine-local execution convenience values only. It must not contain API keys or API-key identifiers; private-key bytes or PEM material; passwords, bearer tokens, signatures, auth headers, cookies, or session tokens; venue authorization state; risk limits or risk-config values; scenario profile values or G selections; canonical Git commits, trees, blobs, or repository-control identities; or deployed N1 persistent-state content. Secret or capability-bearing material requires a separate contract.

#### 1.2.3 Interpreter resolution for adopting consumers

The resolution contract applies to a future wrapper/resolver or other consumer that explicitly adopts `LocalExecutionConfigV1`. It does not retroactively add `-ConfigPath` to the archived V2 launcher.

The effective interpreter source is selected in this strict order:

```text
1. explicit -Python
2. explicit -ConfigPath -> LocalExecutionConfigV1
3. default %LOCALAPPDATA%\ARB\arb-local-config.json
4. halt closed
```

A valid higher-precedence source suppresses evaluation of lower-precedence sources:

- explicit `-Python` has precedence. It is resolved to an absolute path without semantic rewriting and must name an existing file, otherwise halt `PYTHON_EXECUTABLE_NOT_FOUND`. An invalid or nonexistent config path must not defeat it and need not be read.
- with no explicit `-Python`, an explicit `-ConfigPath` is the only config read. Missing, unreadable, malformed, unsupported, or incomplete config halts closed; it never falls through to the default path.
- with neither explicit source, the default path is derived from `%LOCALAPPDATA%`; if that variable is absent or empty, halt `LOCALAPPDATA_UNSET`. No other profile directory is searched.

Prohibited implicit fallback sources:

```text
bare python
py launcher
PATH search
CONDA_PREFIX
CONDA_DEFAULT_ENV
another Conda environment
ARB_CODEX_PYTHON_EXE
Codex environment metadata
registry discovery
network discovery
package-manager discovery
```

Resolution is a deterministic local operation with zero automatic retries, no redirect behavior, and no network request; a resolution failure is terminal for that invocation. An implementing consumer distinguishes at least these stable failure classes, optionally followed by diagnostic detail that downstream logic need not parse:

```text
LOCALAPPDATA_UNSET
CONFIG_NOT_FOUND
CONFIG_READ_FAILED
CONFIG_MALFORMED
CONFIG_SCHEMA_UNSUPPORTED
PYTHON_SECTION_MISSING
PYTHON_EXECUTABLE_MISSING
PYTHON_EXECUTABLE_NOT_FOUND
```

Successful resolution proves only that an interpreter path was selected and exists as a file. It does not prove CPython 3.12, an active `pmresearch` environment, installed dependencies, an authorized repository commit, or any venue, credential, N1, test, or write authorization; each remains a separate gate.

#### 1.2.4 Relationship to the Codex interpreter contract

`ARB_CODEX_PYTHON_EXE` (Section 1.1) remains a distinct Codex-specific contract. `LocalExecutionConfigV1` does not replace, migrate, or supersede it, and neither contract is a fallback for the other.

#### 1.2.5 Archived V2 launcher exception and first migration

The archived launcher `project_archive/r1_d07_2026_09_14/n1_fresh_read_only_state_revalidation_v2/RUN_R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_02.ps1` remains byte-immutable canonical provenance. Its embedded user-specific `-Python` default is a historical, provenance-bound portability exception, not a recommended pattern or new default. The launcher already accepts an explicit `-Python`, which is the supported portability seam.

The first migration uses explicit interpreter forwarding only: the V2 regression tests pass `-Python` bound to the running test interpreter's `sys.executable` on every direct launcher invocation. It adds no tracked config resolver, wrapper, CLI, dependency, or shared configuration framework, and it does not read a local JSON config. A later resolver requires its own task defining writable paths, tests, capability boundaries, and adoption scope.

#### 1.2.6 Forward portability rule (LEC-FWD)

**LEC-FWD-001 (mandatory):** A new canonical executable artifact MUST NOT embed a user-specific absolute path for a machine-local executable or workspace convenience path when that value can be represented by an approved machine-local configuration contract or an explicit runtime parameter. Nonconformance is `MACHINE_LOCAL_PATH_PORTABILITY_CONTRACT_VIOLATION`.

**LEC-FWD-002:** Historical/provenance-bound artifacts are not mass-migrated. An immutable archive may retain a historical user-specific default only when its exact bytes are already a canonical reviewed identity, a supported explicit override exists for the affected value, and active wrappers/tests supply the portable value rather than relying on the stale default. The archived V2 launcher is the first explicit application of this exception.

**LEC-FWD-003:** This rule does not automatically migrate or supersede `ARB_CODEX_PYTHON_EXE`, Codex environment settings, venue credentials, N1 deployment paths, risk configuration, profile selection, or Git/repository identities.

## 2. PowerShell-only local command rule

Commands intended for Gustavo to run locally must be provided in PowerShell syntax by default.

This includes:

- Python programs and one-shot Python commands;
- project runners;
- Python module invocations;
- tests;
- Git inspection and repository support commands;
- hashing and filesystem verification;
- archive inspection;
- environment checks;
- explicitly authorized installation commands.

Examples:

```powershell
python script.py
python -m unittest ...
python -m pytest ...
python -m pip ...
git status --porcelain
```

For multi-line PowerShell commands, use valid PowerShell continuation or native PowerShell constructs. Prefer a single-line command when that is clearer and less error-prone.

Do not provide another shell as the default or as a duplicate alternative unless the active task explicitly requires that shell.

## 3. PowerShell validation and administrative operations

PowerShell is the default local shell for administrative, inspection, verification, hashing, filesystem, Git-support, installation, and project execution commands when the active task separately authorizes the underlying activity.

Typical uses include:

- file size inspection;
- SHA-256 calculation;
- filesystem checks;
- environment/path inspection;
- Git checkout verification;
- Git working-tree validation;
- line-ending diagnosis;
- archive/file inspection;
- creating directories;
- downloading or installing explicitly authorized dependencies/tools;
- Windows-native administration required by an explicitly authorized task.

Examples:

```powershell
(Get-Item .\path\file).Length
(Get-FileHash .\path\file -Algorithm SHA256).Hash.ToLower()
git status --porcelain
```

PowerShell availability does not itself authorize installation, downloads, network access, code changes, tests, or execution.

## 4. Python package installation boundary

No Python package may be installed merely because the local environment can install it.

A package/dependency installation requires the task to authorize the relevant dependency change and, when applicable, package-download network access.

Before an authorized Python package installation, verify the interpreter/environment that will receive the package:

```powershell
Get-Command python
python -c "import sys; print(sys.executable)"
python -m pip --version
```

Prefer interpreter-qualified package operations:

```powershell
python -m pip ...
```

over an unqualified `pip ...`.

Verify that PowerShell resolves Python, pip, and Conda to the intended environment. Do not assume shell activation or directory location proves interpreter identity.

## 5. Conda environment behavior

The default expectation is that Gustavo activates the Miniconda environment before running project Python commands.

Typical prompt form:

```text
(pmresearch) PS C:\b1\kals>
```

Do not assume activation solely from a directory name. When material, verify:

```powershell
$env:CONDA_DEFAULT_ENV
Get-Command python
python -c "import sys; print(sys.executable)"
```

If the active environment is not the expected environment, halt before Python execution unless the active task explicitly permits another environment.

## 6. Windows path conventions

Commands intended for the local Windows environment should use Windows paths and PowerShell-appropriate quoting.

Current ARB local working root:

```text
C:\b1\kals
```

Typical repository path:

```text
C:\b1\kals\ARB
```

Do not assume a POSIX path such as `/home/...` or `/mnt/...` applies to Gustavo's local execution environment.

Paths used inside ChatGPT/tool sandboxes are separate from Gustavo's Windows filesystem and must not be presented as local Windows paths.

## 7. Git and line-ending policy

### 7.1 Git shell

Use PowerShell for Git commands shown to Gustavo unless an exact task explicitly requires another shell.

Examples:

```powershell
git status --porcelain
git rev-parse HEAD
git rev-parse 'HEAD^{tree}'
git rev-parse HEAD:path/to/file
git hash-object .\path\to\file
git diff --summary -- .\path\to\file
git diff --numstat -- .\path\to\file
git check-attr -a -- .\path\to\file
git config --get core.autocrlf
git config --get core.eol
```

Quote Git revision expressions that PowerShell could otherwise interpret specially.

### 7.2 Windows CRLF risk

Windows Git may transform repository LF (`\n`) endings into CRLF (`\r\n`) in the worktree depending on `core.autocrlf`, `.gitattributes`, or related settings.

For ordinary source editing this may be logically harmless. For ARB, some reviewed files are bound to exact:

- raw byte length;
- SHA-256;
- Git blob identity.

When an execution or review gate specifies exact bytes or hashes, logical source equivalence is insufficient. The local worktree bytes must match the reviewed identity exactly.

A typical CRLF symptom is:

- SHA-256 differs from the reviewed file;
- byte length increases by approximately one byte per line;
- the file otherwise appears textually identical.

Do not accept such a mismatch merely because Git can normalize it.

### 7.3 Repository-local LF configuration

For ARB byte-sensitive work on Windows, prefer repository-local configuration:

```powershell
git config core.autocrlf false
git config core.eol lf
```

Do not change global Git line-ending configuration unless a task explicitly requires it.

For a new clone intended for exact-byte execution/review:

```powershell
git clone https://github.com/rigolugo/ARB.git ARB
Set-Location .\ARB
git config core.autocrlf false
git config core.eol lf
```

Then check out or restore the exact authorized commit/path required by the task.

If a file was already materialized with CRLF and exact LF bytes are required, correct only the authorized path:

```powershell
git config core.autocrlf false
git config core.eol lf
git restore --source=HEAD --worktree -- .\path\to\file
```

Do not perform broad `git reset --hard`, repository-wide normalization, or mass re-checkout unless explicitly authorized.

### 7.4 Exact Git-content verification

For an exact repository path, compare the committed blob and local worktree blob:

```powershell
git rev-parse HEAD:path/to/file
git hash-object .\path\to\file
```

Those two blob IDs should match.

Also verify:

```powershell
git rev-parse HEAD
git status --porcelain
```

For byte-sensitive execution, an unexplained modified worktree blocks execution.

If `git status` reports a modification while the two blob IDs match and ordinary diff output is empty, treat it first as index/stat/line-ending bookkeeping. Diagnose it; do not hide it.

Useful diagnostics:

```powershell
git diff --summary -- .\path\to\file
git diff --numstat -- .\path\to\file
git status --porcelain=v2
git check-attr -a -- .\path\to\file
git update-index --refresh
```

Do not use `assume-unchanged` or `skip-worktree` to conceal an unexplained difference.

Do not create a commit merely to make a local exact-byte checkout appear clean.

### 7.5 External byte/SHA-256 verification

When an accepted artifact has an external byte-length/SHA-256 identity, verify it independently of Git:

```powershell
(Get-Item .\path\file).Length
(Get-FileHash .\path\file -Algorithm SHA256).Hash.ToLower()
```

Required identities must match exactly before consuming an authorization-bound execution.

### 7.6 Final byte-sensitive checkout gate

Before any local execution bound to reviewed repository bytes, verify all applicable predicates:

```text
1. HEAD commit equals the authorized commit.
2. Required path Git blob equals HEAD's blob.
3. Required path byte length equals the reviewed byte length.
4. Required path SHA-256 equals the reviewed SHA-256.
5. `git status --porcelain` is clean, unless the task explicitly accepts a narrower state.
6. Repository-local line-ending settings are known when line-ending transformation is material.
```

Stop on any unexplained mismatch.

### 7.7 Git capability boundary

Git availability does not authorize Git activity.

Clone/fetch/checkout/restore, branch creation, staging, commits, pushes, merges, resets, or configuration changes remain subject to the active task authorization.

Repository-local `core.autocrlf` / `core.eol` changes used only to reproduce exact reviewed worktree bytes are operational environment settings; they do not by themselves authorize source changes, staging, commits, or remote changes.

## 8. Command-formatting requirement for agents

When Marco, Bruno, Codex, Claude Code, or another ARB implementer gives Gustavo local commands:

1. use PowerShell syntax by default;
2. label a block `PowerShell` when shell context matters;
3. prefer commands that work in the already activated intended Conda environment;
4. include interpreter/environment verification before material Python execution when ambiguity is possible;
5. use Windows paths for Gustavo's local machine;
6. distinguish local Windows paths from ChatGPT/tool sandbox paths;
7. preserve exact-byte/hash checks when execution is bound to reviewed artifacts;
8. quote Git revision expressions when PowerShell parsing could alter them;
9. for byte-sensitive Windows checkouts, prefer repository-local `core.autocrlf=false` and `core.eol=lf`, then verify commit/blob/byte/SHA-256 identities before execution;
10. do not provide duplicate alternate-shell instructions unless the active task specifically requires them.

## 9. Installation command rule

Installation instructions use PowerShell by default.

However:

- installation must already be authorized by the task;
- any required network access must already be authorized;
- Python-targeted installs must be bound to the intended Conda environment;
- the agent must not treat the ability to install as permission to install;
- no install command may silently alter the canonical repository or project dependency set outside the authorized scope.

If an install changes project dependencies, lockfiles, manifests, or runtime requirements, that is a project/code change and requires the corresponding authorization.

## 10. No authorization inheritance

This environment record describes **how** to express and verify local commands.

It never determines **whether** an action is permitted.

In particular, none of the following are authorized by this file alone:

- network access;
- Kalshi Demo reads;
- Kalshi production reads;
- authenticated access;
- credentials;
- WebSockets;
- writes;
- orders;
- cancellations;
- funding;
- paper/live trading;
- dependency installation;
- tests;
- code changes;
- artifact generation;
- repository commits.

Task-specific authorization remains controlling.
