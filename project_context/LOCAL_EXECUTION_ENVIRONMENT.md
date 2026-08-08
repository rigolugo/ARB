# LOCAL_EXECUTION_ENVIRONMENT

## Purpose

This file records the default local execution environment and command-formatting conventions for the ARB project.

It is an operational convenience record only.

It does **not** grant network access, venue access, credential use, package installation, code changes, test execution, repository writes, Git commits, funding, orders, cancellations, trading, or any other capability. Every activity still requires the exact authorization applicable to that task.

If this file conflicts with `project_context/GUARDRAILS.md`, an exact active Gustavo authorization, or another higher-authority canonical control, the more restrictive higher-authority rule controls.

## 1. Default host environment

Unless Gustavo states otherwise for a specific task, assume the user-operated local environment is:

- operating system: Microsoft Windows;
- primary project shell for Python execution: `cmd.exe`;
- Python environment manager: Miniconda / Conda;
- default active Conda environment for this project: `pmresearch`;
- Python major/minor target: CPython 3.12;
- currently observed local Python version: CPython 3.12.13.

Do not hard-bind future work to patch version `3.12.13` unless a task or accepted specification requires that exact patch version.

Before a task materially depends on the interpreter identity, verify it from the active shell.

Recommended `cmd.exe` checks:

```cmd
where python
python --version
python -c "import sys; print(sys.executable)"
```

When the intended Conda environment is already active, prefer:

```cmd
python ...
```

Do not replace it with the Windows `py` launcher unless a task explicitly requires the launcher.

## 2. Shell rule for Python execution

Python programs, project runners, Python module invocations, Python tests, and Python one-shot execution commands intended for Gustavo to run locally must be provided in `cmd.exe` syntax by default.

Examples include:

```cmd
python script.py
python -m unittest ...
python -m pytest ...
python -m pip ...
```

For multi-line `cmd.exe` commands, use caret continuation:

```cmd
python script.py ^
  --option-a value ^
  --option-b value
```

Do not use PowerShell backticks in commands labeled for `cmd.exe`.

When practical, also provide a single-line `cmd.exe` form for copy/paste reliability.

## 3. PowerShell is available for validation and installation operations

PowerShell may be used for local administrative, inspection, verification, hashing, filesystem, Git-support, and installation commands when the active task separately authorizes the underlying activity.

Typical PowerShell uses include:

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

PowerShell availability does not itself authorize installation, downloads, network access, code changes, or execution.

## 4. Python package installation boundary

No Python package may be installed merely because the local environment can install it.

A package/dependency installation requires the task to authorize the relevant dependency change and, when applicable, package-download network access.

Before an authorized Python package installation, verify the interpreter/environment that will receive the package.

For the active Conda environment, preferred verification from `cmd.exe` is:

```cmd
where python
python -c "import sys; print(sys.executable)"
python -m pip --version
```

Prefer interpreter-qualified package operations such as:

```cmd
python -m pip ...
```

over an unqualified `pip ...` when using pip.

If an installation is intentionally performed from PowerShell, verify that the command resolves to the intended Conda environment or invoke the intended environment/interpreter explicitly. Do not assume PowerShell and `cmd.exe` resolve `python`, `pip`, or `conda` identically.

## 5. Conda environment behavior

The default expectation is that Gustavo activates the Miniconda environment before running project Python commands.

Typical prompt form:

```text
(pmresearch) C:\b1\kals>
```

Do not assume activation solely from a directory name. When material, verify:

```cmd
echo %CONDA_DEFAULT_ENV%
where python
python -c "import sys; print(sys.executable)"
```

If the active environment is not the expected environment, halt before Python execution unless the active task explicitly permits another environment.

## 6. Windows path conventions

Commands intended for the local Windows environment should use Windows paths and shell-appropriate quoting.

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

## 7. Git command shell and line-ending policy

### 7.1 Git shell

Git commands may be run from either `cmd.exe` or PowerShell unless a task explicitly requires one shell.

Prefer shell-neutral Git commands when possible:

```cmd
git status --porcelain
git rev-parse HEAD
git rev-parse HEAD:path/to/file
git hash-object path\to\file
git diff --summary -- path\to\file
git diff --numstat -- path\to\file
git check-attr -a -- path\to\file
git config --get core.autocrlf
git config --get core.eol
```

For Git commands shown across multiple lines:

- `cmd.exe` continuation: `^`
- PowerShell continuation: backtick

Do not mix those continuation syntaxes.

### 7.2 Windows CRLF risk

Windows Git may transform repository LF (`\n`) endings into CRLF (`\r\n`) in the worktree depending on `core.autocrlf`, `.gitattributes`, or related settings.

For ordinary source editing this may be logically harmless. For this project, some reviewed files are bound to exact:

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

```cmd
git config core.autocrlf false
git config core.eol lf
```

Do not change global Git line-ending configuration unless a task explicitly requires it.

For a new clone intended for exact-byte execution/review:

```cmd
git clone https://github.com/rigolugo/ARB.git ARB
cd ARB
git config core.autocrlf false
git config core.eol lf
```

Then checkout or restore the exact authorized commit/path required by the task.

If a file was already materialized with CRLF and exact LF bytes are required, correct only the authorized path:

```cmd
git config core.autocrlf false
git config core.eol lf
git restore --source=HEAD --worktree -- path\to\file
```

Do not perform broad `git reset --hard`, repository-wide normalization, or mass re-checkout unless explicitly authorized.

### 7.4 Exact Git-content verification

For an exact repository path, compare the committed blob and local worktree blob:

```cmd
git rev-parse HEAD:path/to/file
git hash-object path\to\file
```

Those two blob IDs should match.

Also verify:

```cmd
git rev-parse HEAD
git status --porcelain
```

For byte-sensitive execution, an unexplained modified worktree blocks execution.

If `git status` reports a modification while the two blob IDs match and ordinary diff output is empty, treat it first as index/stat/line-ending bookkeeping. Diagnose it; do not hide it.

Useful diagnostics:

```cmd
git diff --summary -- path\to\file
git diff --numstat -- path\to\file
git status --porcelain=v2
git check-attr -a -- path\to\file
git update-index --refresh
```

Do not use `assume-unchanged` or `skip-worktree` to conceal an unexplained difference.

Do not create a commit merely to make a local exact-byte checkout appear clean.

### 7.5 External byte/SHA-256 verification

When an accepted artifact has an external byte-length/SHA-256 identity, verify it independently of Git.

PowerShell:

```powershell
(Get-Item .\path\file).Length
(Get-FileHash .\path\file -Algorithm SHA256).Hash.ToLower()
```

From `cmd.exe`, PowerShell may be invoked when convenient:

```cmd
powershell -NoProfile -Command "(Get-Item '.\path\file').Length; (Get-FileHash '.\path\file' -Algorithm SHA256).Hash.ToLower()"
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

When Marco, Bruno, or Neo gives Gustavo local commands:

1. identify the intended shell when shell syntax matters;
2. default Python execution commands to `cmd.exe`;
3. use `^` for `cmd.exe` line continuation;
4. use PowerShell syntax only in blocks explicitly labeled PowerShell;
5. never mix PowerShell backticks with `cmd.exe` commands;
6. prefer `python` from the already activated intended Conda environment;
7. include interpreter/environment verification before a material Python execution when ambiguity is possible;
8. use Windows paths for Gustavo's local machine;
9. distinguish local Windows paths from ChatGPT sandbox paths;
10. preserve exact-byte/hash checks when execution is bound to reviewed artifacts;
11. Git commands may use either `cmd.exe` or PowerShell, but identify the shell whenever quoting or continuation syntax differs;
12. for byte-sensitive Windows checkouts, prefer repository-local `core.autocrlf=false` and `core.eol=lf`, then verify commit/blob/byte/SHA-256 identities before execution.

## 9. Installation command rule

Installation instructions may be expressed in PowerShell when PowerShell is the more reliable Windows administrative shell.

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
