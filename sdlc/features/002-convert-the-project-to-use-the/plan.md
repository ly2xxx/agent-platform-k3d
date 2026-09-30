<!-- sdlc stage=plan model=glm-5.3:cloud from=intent.md,spec.md@6d49db6 -->
## Approach
The smallest change: add a root `pyproject.toml` that declares the project with exactly the four `requirements.txt` dependencies and their existing lower bounds (plus the minimal `[tool.uv] package = false` uv needs so it never tries to build the unpackaged `app/`), generate and commit `uv.lock` with `uv lock`, rewrite only the `python-tests` job in `.github/workflows/ci.yml` to install with `uv sync --locked` and run the suites with `uv run --with pytest pytest app/tests scripts/tests`, delete `requirements.txt`, add `.venv/` to `.gitignore`, and add a small pytest module (`tests/test_uv_migration.py`) that pins every one of those facts with `tomllib` and plain file reads so the checks need no network.

## Coverage

| Done when (intent.md) | Spec behaviours | Phase |
| :-- | :-- | :-- |
| A `pyproject.toml` exists declaring the project and the dependencies currently listed in `requirements.txt` (fastapi, httpx, numpy, pyyaml). | 1 | Phase 1 |
| A `uv.lock` is committed and pins those dependencies reproducibly. | 2, 3 | Phase 2 |
| CI installs dependencies and runs the test suite using uv commands. | 5, 6, 7 | Phase 3 |
| `requirements.txt` is no longer used by the project's workflow; installing via `uv sync` (or equivalent) yields a working environment. | 4, 8 | Phases 3 and 4 |
| The existing tests still pass. | 8 | Phase 4 |

## Phase 1: Declare the project in pyproject.toml
<!-- phase: 1 -->
<!-- targets: pyproject.toml, tests/test_uv_migration.py -->
<!-- frozen: requirements.txt, .github/workflows/ci.yml, .gitignore, app/__init__.py, app/main.py, app/order_book.py, app/pricing.py, app/tests/*, scripts/tests/* -->

**Goal:** The repository root has a `pyproject.toml` declaring a project whose `[project]` dependencies are exactly the four packages from `requirements.txt` with their existing lower bounds, and a new test module proves it by parsing the file.

**Changes:**
- `pyproject.toml` (new, repository root) — create with exactly this content:

```toml
[project]
name = "besa-agent-platform"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.110",
    "httpx>=0.27",
    "numpy>=1.26",
    "pyyaml>=6.0",
]

# `app/` is not a distributable package, so uv must install only the
# dependencies above and never try to build the project itself.
[tool.uv]
package = false
```

  Notes: `requires-python = ">=3.12"` matches the `python-version: "3.12"` CI already configures; no new constraint. `[tool.uv] package = false` is the one tool section uv needs so `uv lock`/`uv sync` resolve dependencies without a build backend (there is no `[build-system]`, per the spec). No other sections.
- `tests/test_uv_migration.py` (new) — create with exactly this content (stdlib only; `tomllib` is in the standard library on Python ≥3.11):

```python
"""Tests for the uv migration: pyproject, lockfile, CI workflow, gitignore."""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EXPECTED_DEPENDENCIES = [
    "fastapi>=0.110",
    "httpx>=0.27",
    "numpy>=1.26",
    "pyyaml>=6.0",
]

def _load_pyproject() -> dict:
    with (ROOT / "pyproject.toml").open("rb") as f:
        return tomllib.load(f)

def test_pyproject_declares_project_and_exact_dependencies() -> None:
    """Spec behaviour 1: project declared with exactly the four requirements.txt deps."""
    project = _load_pyproject()["project"]
    assert project["name"] == "besa-agent-platform"
    assert project["version"] == "0.1.0"
    assert project["requires-python"] == ">=3.12"
    assert sorted(project["dependencies"]) == sorted(EXPECTED_DEPENDENCIES)

def test_pyproject_has_no_build_system_section() -> None:
    """Spec Interfaces: no build-system section beyond what uv needs."""
    data = _load_pyproject()
    assert "build-system" not in data
    assert "project" in data
```

  No `__init__.py` in `tests/`; the file is self-contained (locates the repo root via `Path(__file__).resolve().parents[1]`), needs no fixtures, network, or teardown.

**Definition of done:**
- [ ] `tests/test_uv_migration.py::test_pyproject_declares_project_and_exact_dependencies`: proves spec behaviour 1 — parses `pyproject.toml` with `tomllib` and asserts the project name, version, `requires-python == ">=3.12"`, and that the sorted `[project] dependencies` equal the sorted four `requirements.txt` entries verbatim (`fastapi>=0.110`, `httpx>=0.27`, `numpy>=1.26`, `pyyaml>=6.0`); exact code above.
- [ ] `tests/test_uv_migration.py::test_pyproject_has_no_build_system_section`: proves the spec's Interfaces constraint (no `build-system` key).
- [ ] `python -m pytest app/tests -q` still passes with zero changes to `app/` (regression guard).

**Verify:**
```bash
python -m pytest tests/test_uv_migration.py -v
python -m pytest app/tests -q
```

**Attempt budget:** 3 failed attempts, then stop and revise this plan instead of retrying.

## Phase 2: Generate and commit uv.lock
<!-- phase: 2 -->
<!-- targets: uv.lock, tests/test_uv_migration.py -->
<!-- frozen: pyproject.toml, requirements.txt, .github/workflows/ci.yml, .gitignore, app/__init__.py, app/main.py, app/order_book.py, app/pricing.py, app/tests/*, scripts/tests/* -->

**Goal:** A machine-generated `uv.lock` is committed at the repository root, pins fully resolved versions for the four direct dependencies and their transitive dependencies, and `uv lock --check` succeeds without re-resolving.

**Changes:**
- `uv.lock` (new, repository root) — generated, never hand-edited: run `uv lock` from the repository root once (this is the one required terminal command in this phase; approve it at the prompt). It resolves the four declared dependencies and writes `uv.lock`. Commit the file exactly as generated. If `uv` is not installed on the builder machine, install it first by the user's normal method; do not commit any uv config beyond this file.
- `tests/test_uv_migration.py` — append these functions (uses the existing `EXPECTED_DEPENDENCIES`, `ROOT`, `re`, `tomllib`):

```python
def _load_uv_lock() -> dict:
    with (ROOT / "uv.lock").open("rb") as f:
        return tomllib.load(f)

def _is_pinned(version: str) -> bool:
    return bool(re.fullmatch(r"\d+(\.\d+)*", version))

def test_uv_lock_pins_all_direct_dependencies() -> None:
    """Spec behaviour 2: fastapi, httpx, numpy, pyyaml pinned at concrete versions."""
    packages = {p["name"].lower(): p["version"] for p in _load_uv_lock()["package"]}
    for dep in EXPECTED_DEPENDENCIES:
        name = re.split(r"[><=!~\[]", dep)[0].strip().lower()
        assert name in packages, f"{name} missing from uv.lock"
        assert _is_pinned(packages[name]), packages[name]

def test_uv_lock_pins_every_transitive_package() -> None:
    """Spec behaviour 2: every entry in uv.lock is a fully resolved version."""
    lock_packages = _load_uv_lock()["package"]
    names = [p["name"] for p in lock_packages]
    assert len(names) == len(set(names))
    for p in lock_packages:
        assert _is_pinned(p["version"]), (p["name"], p["version"])

def test_uv_lock_is_not_gitignored() -> None:
    """Spec behaviour 2: uv.lock is committed, not ignored."""
    for raw in (ROOT / ".gitignore").read_text().splitlines():
        assert raw.strip() != "uv.lock"
```

**Definition of done:**
- [ ] `tests/test_uv_migration.py::test_uv_lock_pins_all_direct_dependencies`: proves spec behaviour 2 for the direct deps — parses `uv.lock` with `tomllib`, builds a `{name: version}` map from the `[[package]]` entries, and asserts each of the four dependency names extracted from `EXPECTED_DEPENDENCIES` is present with a concrete `X.Y[.Z]` version (no range operators); exact code above.
- [ ] `tests/test_uv_migration.py::test_uv_lock_pins_every_transitive_package`: proves transitive dependencies are also pinned (every version matches `\d+(\.\d+)*`, no duplicate package entries).
- [ ] `tests/test_uv_migration.py::test_uv_lock_is_not_gitignored`: proves the lockfile is not excluded by `.gitignore`.
- [ ] `uv lock --check` exits 0: proves spec behaviour 3 (lockfile consistent with `pyproject.toml`, no re-resolving) and that the lock matches the committed `pyproject.toml` from Phase 1.

**Verify:**
```bash
uv lock --check
python -m pytest tests/test_uv_migration.py -v
python -m pytest app/tests -q
```

**Attempt budget:** 3 failed attempts, then stop and revise this plan instead of retrying.

## Phase 3: Switch CI to uv and retire requirements.txt
<!-- phase: 3 -->
<!-- targets: .github/workflows/ci.yml, .gitignore, requirements.txt, tests/test_uv_migration.py -->
<!-- frozen: pyproject.toml, uv.lock, app/__init__.py, app/main.py, app/order_book.py, app/pricing.py, app/tests/*, scripts/tests/* -->

**Goal:** The `python-tests` CI job installs with `uv sync --locked` and runs both existing suites through `uv run`, `requirements.txt` is deleted, `.gitignore` ignores `.venv/`, and tests prove all of it by reading the files as text.

**Changes:**
- `.github/workflows/ci.yml` — replace the entire `python-tests` job with exactly:

```yaml
  python-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install uv
        run: pip install uv
      - name: Install dependencies from the lockfile
        run: uv sync --locked
      - name: Run the test suites through uv
        run: uv run --with pytest pytest app/tests scripts/tests
```

  Every other job (`chart`, `tests`, `secrets`) is untouched, including the `tests` job's `pip install pyyaml` / `python -m unittest discover -s scripts/tests` step (it does not install from `requirements.txt`; see Open questions). `--with pytest` is uv's equivalent of today's ad-hoc `pip install ... pytest`, keeping pytest out of the project's four declared dependencies and out of any `[dependency-groups]` section, per the spec.
- `requirements.txt` — delete it (`git rm requirements.txt`).
- `.gitignore` — append these two lines at the end (skip if a `.venv` entry already exists):

```
# uv's default virtual environment directory
.venv/
```
- `tests/test_uv_migration.py` — append:

```python
def test_requirements_txt_is_deleted() -> None:
    """Spec behaviour 4: requirements.txt no longer exists."""
    assert not (ROOT / "requirements.txt").exists()

def test_ci_installs_and_tests_through_uv() -> None:
    """Spec behaviours 5 and 6: CI installs via uv and runs the suites through uv."""
    content = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "requirements.txt" not in content
    assert "python -m pytest" not in content
    assert "uv sync" in content
    assert "uv run --with pytest pytest app/tests scripts/tests" in content

def test_gitignore_ignores_uv_venv() -> None:
    """Spec behaviour 7: .venv is gitignored so uv sync artifacts stay local."""
    lines = [line.strip() for line in (ROOT / ".gitignore").read_text().splitlines()]
    assert ".venv" in lines or ".venv/" in lines
```

**Definition of done:**
- [ ] `test ! -e requirements.txt` passes: spec behaviour 4, the file is gone.
- [ ] `tests/test_uv_migration.py::test_ci_installs_and_tests_through_uv`: proves spec behaviours 5 and 6 — reads `.github/workflows/ci.yml` as text and asserts no `requirements.txt` reference, no bare `python -m pytest`, an installation step containing `uv sync`, and the exact `uv run --with pytest pytest app/tests scripts/tests` invocation (CI already runs `scripts/tests`, so criterion 6 covers it).
- [ ] `tests/test_uv_migration.py::test_gitignore_ignores_uv_venv`: proves spec behaviour 7 (`.venv` or `.venv/` line present in `.gitignore`).
- [ ] `uv lock --check` still passes: deleting `requirements.txt` and touching CI did not disturb the lock.

**Verify:**
```bash
test ! -e requirements.txt
uv lock --check
python -m pytest tests/test_uv_migration.py -v
python -m pytest app/tests -q
```

**Attempt budget:** 3 failed attempts, then stop and revise this plan instead of retrying.

## Phase 4: Prove the existing suites pass and guard against regressions
<!-- phase: 4 -->
<!-- targets: tests/test_uv_migration.py -->
<!-- frozen: pyproject.toml, uv.lock, .github/workflows/ci.yml, .gitignore, app/__init__.py, app/main.py, app/order_book.py, app/pricing.py, app/tests/*, scripts/tests/* -->

**Goal:** The existing `app/tests` and `scripts/tests` suites pass unmodified under the migrated setup (run exactly as CI runs them), and a final guard test asserts no workflow file anywhere outside the feature documents still references `requirements.txt`.

**Changes:**
- `tests/test_uv_migration.py` — append:

```python
def test_no_requirements_txt_references_outside_feature_docs() -> None:
    """Spec behaviour 4: nothing outside the feature docs still uses requirements.txt."""
    skip_dir_names = {".git", ".venv", "__pycache__", ".pytest_cache", "sdlc", "rendered"}
    text_suffixes = {".py", ".yml", ".yaml", ".toml", ".md", ".txt", ".ps1",
                     ".cfg", ".ini", ".tpl", ""}
    offenders: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        rel_parts = path.relative_to(ROOT).parts
        if any(part in skip_dir_names for part in rel_parts[:-1]):
            continue
        if path.suffix not in text_suffixes:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, ValueError):
            continue
        if "requirements.txt" in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []
```

  No fixtures, no network, no teardown: pure filesystem reads. `sdlc/` is skipped because this plan and the feature documents legitimately name the file.
- No other files change; the suite run in Verify uses the untouched `app/tests/*` and `scripts/tests/*` files, proving the migration required no test modification (spec behaviour 8).

**Definition of done:**
- [ ] `tests/test_uv_migration.py::test_no_requirements_txt_references_outside_feature_docs`: proves `requirements.txt` is fully retired from the workflow — walks every text file in the repo (skipping `.git`, `.venv`, caches, `rendered/`, and `sdlc/`) and asserts none mentions `requirements.txt`.
- [ ] `python -m pytest app/tests scripts/tests -q` passes: proves spec behaviour 8 — both suites CI runs today pass without any modification to their files, in the environment built from `pyproject.toml`/`uv.lock`.
- [ ] `uv lock --check` passes on the finished state: end-to-end consistency of `pyproject.toml` and `uv.lock`.

**Verify:**
```bash
uv lock --check
python -m pytest tests/test_uv_migration.py -v
python -m pytest app/tests scripts/tests -q
```

**Attempt budget:** 3 failed attempts, then stop and revise this plan instead of retrying.

## Risks
- **The verify harness may install the project with `pip install .`** rather than uv; with no `[build-system]` and `[tool.uv] package = false`, setuptools' flat-layout discovery would fail. Phase 1's Verify (run against a harness-built environment) catches this immediately; the remedy would be revising the plan to add a minimal build backend, which would need a spec amendment.
- **`uv` may be absent (or older than `--check`) in the verify environment.** Phase 2's `uv lock --check` catches it. Fallback if so: `uv lock --locked` on older versions, or restructuring behaviour 3's proof as a `tomllib` comparison of the lock's recorded requirements against `pyproject.toml`.
- **`uv lock --check` could want network on a cold cache.** Phase 2's Verify catches it; the lock is consistent by construction, so a failure means the environment, not the lock, and the plan gets revised.
- **Builder's uv version may emit a lock revision the verify env's uv dislikes.** Phase 2's Verify (`uv lock --check`) catches the mismatch on the committed lockfile.
- **`scripts/tests` may secretly require `helm`.** CI's `python-tests` job already runs them under plain pytest without helm, so they must skip or pass; Phase 4's `python -m pytest app/tests scripts/tests -q` is the check that would catch any local-environment difference (a pre-existing condition, not one this plan introduces).
- **CI's `uv run --with pytest` needs network** to fetch pytest on the runner. No Verify block depends on it (they use `python -m pytest`), so only the CI run itself is exposed, exactly as today's `pip install ... pytest` is.
- **Deleting `requirements.txt` or editing CI could leave a stale reference** (e.g. in docs). Phase 4's guard test catches it.

## Open questions
- **Is uv available in the verification environment?** Assumed yes: "How verification runs" installs the project from `pyproject.toml`, which after this migration is a uv-native operation. If not, Phase 2's Verify fails at the first attempt and the plan is revised (see Risks).
- **Project name and `requires-python`:** assumed `besa-agent-platform` (the Helm chart / repo name, a valid PEP 508 name) and `>=3.12` (the version CI's `setup-python` pins). No new Python constraint is invented.
- **`[tool.uv] package = false`:** the spec's Interfaces example omits it, but it is required for uv to resolve and sync dependencies without a build backend, since `app/` is not a distributable package and the spec forbids a `[build-system]`. Treated as "what uv needs for dependency resolution", which the spec allows.
- **pytest provisioning:** per the spec's own assumption, no `[dependency-groups]` is added; pytest stays ad hoc, now via `uv run --with pytest` instead of `pip install ... pytest`.
- **The `tests` CI job (chart/manifests)** keeps `pip install pyyaml` and `python -m unittest discover -s scripts/tests`. It never installs from `requirements.txt`, and behaviour 6 is satisfied by the `python-tests` job invoking both suites through `uv run`. Assumed this is the intended reading of "changes to ci.yml" in the spec's Interfaces.
- **Fate of `requirements.txt`:** deleted, per the intent's own assumption.

## Hand back
When every phase is built and its Verify block passes:
1. Create `sdlc/features/002-convert-the-project-to-use-the/build-log.md` with one section per phase, in order. Head each one `## Phase <n>: <title>`, then list the files changed, the Verify command you ran and its result, and any deviation from this plan (or "none").
2. Commit it and push it to `feature/002-convert-the-project-to-use-the`.

Commit only this plan's targets and `build-log.md`. Leave every other file alone, including other features' documents under `sdlc/features/`, even for formatting; verification fails on any file outside the targets.

The pipeline waits for this file. Once it has a section for every phase, it verifies the whole branch and opens the pull request.
