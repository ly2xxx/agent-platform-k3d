<!-- sdlc stage=plan model=glm-5.3:cloud from=intent.md,spec.md@b675011 -->
## Approach
Add a minimal root-level `pyproject.toml` (only a `[project]` table: name `app`, version `0.1.0`, `requires-python = ">=3.12"` matching the Python version `ci.yml` already pins, and exactly the four dependencies from `requirements.txt` with unchanged lower bounds), generate `uv.lock` with `uv lock` and commit it, switch the `python-tests` CI job from `pip install -r requirements.txt pytest` + `python -m pytest` to `setup-uv` + `uv lock --check` + `uv sync` + `uv run --with pytest pytest app/tests scripts/tests`, add `.venv/` to `.gitignore`, and delete `requirements.txt` — with structural pytest tests for every step so each phase proves itself with `python -m pytest` even on machines without uv installed.

## Coverage

| Done when (intent.md) | Spec behaviours | Phase |
| :-- | :-- | :-- |
| A `pyproject.toml` exists declaring the project and the dependencies currently listed in `requirements.txt` (fastapi, httpx, numpy, pyyaml). | 1 | Phase 1 |
| A `uv.lock` is committed and pins those dependencies reproducibly. | 2, 3 | Phase 1 (lock generated + structural tests); Phase 2 (`uv lock --check` step in CI proves it without re-resolving) |
| CI installs dependencies and runs the test suite using uv commands. | 5, 6 | Phase 2 |
| `requirements.txt` is no longer used by the project's workflow; installing via `uv sync` (or equivalent) yields a working environment. | 4, 7, 8 | Phase 2 (uv sync in CI, `.venv/` ignored); Phase 3 (file deleted); the working-environment proof is the verify env installed from `pyproject.toml` plus the CI `uv sync` run on the branch |
| The existing tests still pass. | 8 | Phases 1–3 (each Verify block runs them); final verification runs the whole suite |

## Phase 1: pyproject.toml and uv.lock
<!-- phase: 1 -->
<!-- targets: pyproject.toml, uv.lock, tests/test_uv_lock.py -->
<!-- frozen: requirements.txt, .gitignore, .github/workflows/ci.yml, app/**, scripts/tests/** -->

**Goal:** The repository root has a `pyproject.toml` declaring exactly the project and its four former `requirements.txt` dependencies, and a committed `uv.lock` pinning them, both proven by tests that parse the two files.

**Changes:**
- `pyproject.toml` (new, repository root): create it with exactly this content and nothing else — no `[build-system]`, no `[tool]`, no other sections:
  ```toml
  [project]
  name = "app"
  version = "0.1.0"
  requires-python = ">=3.12"
  dependencies = [
      "fastapi>=0.110",
      "httpx>=0.27",
      "numpy>=1.26",
      "pyyaml>=6.0",
  ]
  ```
  (`>=3.12` because `.github/workflows/ci.yml` pins `python-version: "3.12"`; the four entries and lower bounds are copied verbatim from `requirements.txt`.)
- `uv.lock` (new, repository root): generated, never hand-edited. Build-time terminal command (needs network; expect an approval prompt): run `uv lock` at the repository root with any uv release from the last year (`pip install uv` into the active environment is acceptable if uv is missing). Then run `uv lock --check`; it must exit 0. Do not add `uv.lock` to `.gitignore`; never commit a `.venv/` directory if you create one.
- Build-time environment note (no file change): if the build machine's `python` lacks the project dependencies, run `uv sync && uv pip install pytest` once and prepend `.venv/bin` to `PATH` (or `source .venv/bin/activate`) so the Verify commands' `python` resolves to that interpreter. `.venv/` is never committed.
- `tests/test_uv_lock.py` (new): create with exactly this content:
  ```python
  """Phase 1: pyproject.toml declares the project; uv.lock pins it reproducibly."""
  import re
  import tomllib
  from pathlib import Path

  ROOT = Path(__file__).resolve().parents[1]

  EXPECTED_DEPENDENCIES = {
      "fastapi": ">=0.110",
      "httpx": ">=0.27",
      "numpy": ">=1.26",
      "pyyaml": ">=6.0",
  }


  def _normalize(name: str) -> str:
      """PEP 503 normalization, matching how uv writes package names in the lock."""
      return re.sub(r"[-_.]+", "-", name).lower()


  def _pyproject() -> dict:
      with (ROOT / "pyproject.toml").open("rb") as handle:
          return tomllib.load(handle)


  def _lock() -> dict:
      with (ROOT / "uv.lock").open("rb") as handle:
          return tomllib.load(handle)


  def _parse_requirement(entry) -> tuple[str, str]:
      """Accept both 'name>=1.0' strings and {name=..., specifier=...} tables."""
      if isinstance(entry, str):
          match = re.match(r"^([A-Za-z0-9._-]+)\s*(.*)$", entry.strip())
          return _normalize(match.group(1)), match.group(2)
      return _normalize(entry["name"]), str(entry.get("specifier", ""))


  def _dependency_name(entry) -> str:
      """Accept both plain-string and {name = ...} dependency entries."""
      return _normalize(entry if isinstance(entry, str) else entry["name"])


  def test_pyproject_declares_project():
      project = _pyproject()["project"]
      assert project["name"] == "app"
      assert project["version"] == "0.1.0"
      assert project["requires-python"] == ">=3.12"


  def test_pyproject_dependencies_are_exactly_the_former_four():
      parsed = dict(_parse_requirement(d) for d in _pyproject()["project"]["dependencies"])
      assert parsed == EXPECTED_DEPENDENCIES


  def test_pyproject_has_no_extra_sections():
      assert set(_pyproject()) == {"project"}


  def test_uv_lock_pins_each_dependency():
      lock = _lock()
      packages = {_normalize(p["name"]): p for p in lock["package"]}
      for name in EXPECTED_DEPENDENCIES:
          assert name in packages, f"uv.lock has no entry for {name}"
          version = packages[name]["version"]
          assert re.fullmatch(r"\d+(\.\d+)*", version), (
              f"{name} is not pinned to an exact version: {version!r}"
          )


  def test_uv_lock_requires_python_matches_pyproject():
      assert _lock()["requires-python"] == _pyproject()["project"]["requires-python"]


  def test_uv_lock_is_consistent_with_pyproject():
      lock = _lock()
      root = next(p for p in lock["package"] if _normalize(p["name"]) == "app")
      declared = {_dependency_name(d) for d in root["dependencies"]}
      assert declared == set(EXPECTED_DEPENDENCIES)
      requires_dist = root.get("metadata", {}).get("requires-dist")
      if requires_dist is not None:
          assert dict(_parse_requirement(r) for r in requires_dist) == EXPECTED_DEPENDENCIES
  ```

**Definition of done:**
- [ ] `tests/test_uv_lock.py::test_pyproject_declares_project`: proves spec behaviour 1 — parses `pyproject.toml` with `tomllib` and asserts `project.name == "app"`, `project.version == "0.1.0"`, `project.requires-python == ">=3.12"`.
- [ ] `tests/test_uv_lock.py::test_pyproject_dependencies_are_exactly_the_former_four`: proves behaviour 1 — the parsed dependency dict equals exactly `{"fastapi": ">=0.110", "httpx": ">=0.27", "numpy": ">=1.26", "pyyaml": ">=6.0"}`, so no bounds changed and nothing was added.
- [ ] `tests/test_uv_lock.py::test_pyproject_has_no_extra_sections`: proves the Interfaces constraint — top-level tables are exactly `{"project"}`.
- [ ] `tests/test_uv_lock.py::test_uv_lock_pins_each_dependency`: proves behaviour 2 — each of the four names appears in a `[[package]]` entry whose `version` matches `^\d+(\.\d+)*$` (fully pinned).
- [ ] `tests/test_uv_lock.py::test_uv_lock_requires_python_matches_pyproject`: proves behaviour 2 — the lock's `requires-python` equals the pyproject's.
- [ ] `tests/test_uv_lock.py::test_uv_lock_is_consistent_with_pyproject`: proves behaviour 3 structurally (the machine-readable emulation of `uv lock --check`) — the root `app` package in `uv.lock` depends on exactly the four names, and its `requires-dist` metadata matches the pyproject dependencies when present.
- [ ] All six tests are pure file reads: no fixtures, no background processes, no teardown needed.
- [ ] Observable check: `uv lock --check` exits 0 at the repository root during the build (run once, after `uv lock`); Phase 2 adds the same command to CI so it keeps being proven.

**Verify:**
```bash
python -m pytest tests/test_uv_lock.py -v
python -m pytest app/tests -q
```

**Attempt budget:** 3 failed attempts, then stop and revise this plan instead of retrying.

## Phase 2: CI through uv and `.venv` ignored
<!-- phase: 2 -->
<!-- targets: .github/workflows/ci.yml, .gitignore, tests/test_ci_workflow.py -->
<!-- frozen: pyproject.toml, uv.lock, requirements.txt, app/**, scripts/tests/**, tests/test_uv_lock.py -->

**Goal:** The `python-tests` CI job installs and tests through uv commands with no reference to `requirements.txt`, and `.gitignore` ignores `.venv/` while `uv.lock` stays trackable.

**Changes:**
- `.github/workflows/ci.yml`: replace the entire `python-tests` job (and only that job — do not touch the `chart`, `tests`, or `secrets` jobs, the triggers, or the runners). Replace:
  ```yaml
    python-tests:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - uses: actions/setup-python@v5
          with:
            python-version: "3.12"
        - run: pip install -r requirements.txt pytest
        - run: python -m pytest app/tests scripts/tests
  ```
  with:
  ```yaml
    python-tests:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - uses: astral-sh/setup-uv@v5
          with:
            python-version: "3.12"
        - name: Lockfile is current
          run: uv lock --check
        - name: Install pinned dependencies
          run: uv sync
        - name: Unit tests
          run: uv run --with pytest pytest app/tests scripts/tests
  ```
  `setup-uv` with `python-version: "3.12"` provides both uv and a managed Python 3.12 (same version the job used before); `uv sync` installs from `uv.lock`; `--with pytest` supplies pytest ephemerally, keeping pytest out of the project dependencies and introducing no `[dependency-groups]` section (per the spec's open-question assumption); `uv lock --check` makes criterion 3 a runtime proof on every CI run.
- `.gitignore`: append the single line `.venv/` (with the file's existing trailing-newline style preserved). If an equivalent `.venv` entry already exists, leave the file otherwise unchanged. Do not add anything else and do not add `uv.lock`.
- `tests/test_ci_workflow.py` (new): create with exactly this content:
  ```python
  """Phase 2: CI installs and tests through uv; .venv is gitignored."""
  import re
  import subprocess
  from pathlib import Path

  import yaml

  ROOT = Path(__file__).resolve().parents[1]
  CI = ROOT / ".github" / "workflows" / "ci.yml"


  def _python_tests_job() -> dict:
      workflow = yaml.safe_load(CI.read_text())
      return workflow["jobs"]["python-tests"]


  def _run_steps(job: dict) -> list:
      return [s["run"] for s in job["steps"] if isinstance(s, dict) and "run" in s]


  def test_workflow_never_mentions_requirements_txt():
      assert "requirements.txt" not in CI.read_text()


  def test_python_tests_installs_with_uv_sync_and_no_pip():
      steps = _run_steps(_python_tests_job())
      assert any(re.search(r"(^|\s)uv sync(\s|$)", s) for s in steps)
      assert not any("pip install" in s for s in steps)


  def test_python_tests_verifies_lockfile_is_current():
      steps = _run_steps(_python_tests_job())
      assert any("uv lock --check" in s for s in steps)


  def test_python_tests_runs_suites_through_uv_run_pytest():
      steps = _run_steps(_python_tests_job())
      pytest_steps = [s for s in steps if "pytest" in s]
      assert pytest_steps, "expected at least one pytest step"
      assert all("uv run" in s for s in pytest_steps)
      assert not any(re.search(r"(^|\s)python -m pytest", s) for s in steps)
      joined = "\n".join(pytest_steps)
      assert "app/tests" in joined
      assert "scripts/tests" in joined


  def test_gitignore_lists_venv():
      lines = (ROOT / ".gitignore").read_text().splitlines()
      assert ".venv/" in [line.strip() for line in lines]


  def test_venv_directory_is_gitignored():
      result = subprocess.run(["git", "check-ignore", "-q", ".venv"], cwd=ROOT)
      assert result.returncode == 0


  def test_uv_lock_is_not_gitignored():
      result = subprocess.run(["git", "check-ignore", "-q", "uv.lock"], cwd=ROOT)
      assert result.returncode != 0
  ```

**Definition of done:**
- [ ] `tests/test_ci_workflow.py::test_workflow_never_mentions_requirements_txt`: proves spec behaviour 5 — the string `requirements.txt` appears nowhere in `ci.yml`, so no step installs from it.
- [ ] `tests/test_ci_workflow.py::test_python_tests_installs_with_uv_sync_and_no_pip`: proves behaviour 5 — a `python-tests` step runs `uv sync`, and no `python-tests` step runs `pip install`.
- [ ] `tests/test_ci_workflow.py::test_python_tests_verifies_lockfile_is_current`: proves behaviour 3 at runtime — CI runs `uv lock --check` every build.
- [ ] `tests/test_ci_workflow.py::test_python_tests_runs_suites_through_uv_run_pytest`: proves behaviour 6 — both suites CI already runs (`app/tests` and `scripts/tests`, matching the current `python -m pytest app/tests scripts/tests` step) are invoked through `uv run ... pytest`, never via bare `python -m pytest`.
- [ ] `tests/test_ci_workflow.py::test_gitignore_lists_venv` and `::test_venv_directory_is_gitignored`: prove behaviour 7 — `.venv/` is listed in `.gitignore` and `git check-ignore` accepts `.venv`. No cleanup needed: `git check-ignore` never reads whether the path exists.
- [ ] `tests/test_ci_workflow.py::test_uv_lock_is_not_gitignored`: proves behaviour 2's "committed, not gitignored" half — `git check-ignore uv.lock` returns non-zero.
- [ ] All tests are file reads plus short-lived `git check-ignore` subprocesses: no servers, threads, or fixtures to tear down. PyYAML is already a project dependency, so `import yaml` needs nothing new.
- [ ] Observable check: behaviour 8's end-to-end run happens as the CI run on this branch's pull request; locally it is proven structurally by the tests above.

**Verify:**
```bash
python -m pytest tests/test_ci_workflow.py -v
python -m pytest app/tests -q
test -z "$(grep -n requirements.txt .github/workflows/ci.yml || true)"
```

**Attempt budget:** 3 failed attempts, then stop and revise this plan instead of retrying.

## Phase 3: Retire requirements.txt
<!-- phase: 3 -->
<!-- targets: requirements.txt, tests/test_requirements_retired.py -->
<!-- frozen: pyproject.toml, uv.lock, .github/workflows/ci.yml, .gitignore, app/**, scripts/tests/**, tests/test_uv_lock.py, tests/test_ci_workflow.py -->

**Goal:** `requirements.txt` is deleted from the repository and nothing references it, while `pyproject.toml` and `uv.lock` remain the single source of dependencies and the existing suites still pass.

**Changes:**
- `requirements.txt`: delete the file. Nothing references it after Phase 2 (Phase 2's `test_workflow_never_mentions_requirements_txt` proves CI does not, and no other workflow or script in the repository reads it — the `tests` CI job installs `pyyaml` directly, not from the file).
- `tests/test_requirements_retired.py` (new): create with exactly this content:
  ```python
  """Phase 3: requirements.txt is retired; pyproject/uv.lock are the single source."""
  import re
  import tomllib
  from pathlib import Path

  ROOT = Path(__file__).resolve().parents[1]

  EXPECTED = {"fastapi", "httpx", "numpy", "pyyaml"}


  def _normalize(name: str) -> str:
      return re.sub(r"[-_.]+", "-", name).lower()


  def test_requirements_txt_is_deleted():
      assert not (ROOT / "requirements.txt").exists()


  def test_pyproject_still_declares_exactly_the_four_dependencies():
      with (ROOT / "pyproject.toml").open("rb") as handle:
          deps = tomllib.load(handle)["project"]["dependencies"]
      names = {_normalize(re.match(r"^([A-Za-z0-9._-]+)", d).group(1)) for d in deps}
      assert names == EXPECTED


  def test_uv_lock_still_pins_the_four_dependencies():
      with (ROOT / "uv.lock").open("rb") as handle:
          lock = tomllib.load(handle)
      names = {_normalize(p["name"]) for p in lock["package"]}
      assert EXPECTED <= names
  ```

**Definition of done:**
- [ ] `tests/test_requirements_retired.py::test_requirements_txt_is_deleted`: proves spec behaviour 4 — `requirements.txt` does not exist at the repository root.
- [ ] `tests/test_requirements_retired.py::test_pyproject_still_declares_exactly_the_four_dependencies` and `::test_uv_lock_still_pins_the_four_dependencies`: regression guards proving behaviours 1 and 2 still hold after the retirement — the four dependencies live only in `pyproject.toml`/`uv.lock`, with nothing lost in the deletion.
- [ ] All tests are pure file reads: no fixtures, no teardown.
- [ ] Observable check: `test ! -e requirements.txt` in the Verify block, plus the existing suites (`app/tests`, `scripts/tests`) passing in an environment installed from `pyproject.toml` — the local equivalent of behaviour 8's "uv sync yields a working environment" (the authoritative `uv sync` proof is the Phase 2 CI job on the pull request).

**Verify:**
```bash
python -m pytest tests/test_requirements_retired.py -v
python -m pytest app/tests scripts/tests -q
test ! -e requirements.txt
```

**Attempt budget:** 3 failed attempts, then stop and revise this plan instead of retrying.

## Risks
- **uv.lock TOML layout varies across uv versions** (`requires-dist` as inline tables vs strings, `editable` vs `virtual` source for the root). Phase 1's tests parse tolerantly (string-or-table helpers, name-based root lookup) and assert invariants, and the authoritative check is the builder's `uv lock --check` in Phase 1 plus the `uv lock --check` CI step in Phase 2 — a format surprise is caught at Phase 1's Verify or in Phase 2's CI run, not silently.
- **The verify job pip-installs the project from the new `pyproject.toml`**, exercising the implicit setuptools backend and flat-layout auto-discovery. `app` is the only top-level directory with an `__init__.py` (`tests/` deliberately has none), so discovery is unambiguous; if packaging failed, Phase 1's Verify block would fail immediately and loudly.
- **Environment parity drift**: the verify env resolves the lower bounds via pip while CI pins via `uv sync` from `uv.lock`. The committed lock plus `uv lock --check` in CI keep them convergent; divergence would surface as a CI failure on the branch, which is exactly behaviour 8's runtime proof.
- **`git check-ignore` (Phase 2 tests) needs git**, which every verification checkout is by definition (the pipeline itself uses `git show <tag>:<path>`). The `.venv/` requirement is additionally proven without git by `test_gitignore_lists_venv`, so a git-less anomaly would still be caught on the lock side only.
- **PyYAML parses the workflow's `on:` key as boolean `True`**; the Phase 2 tests traverse only `["jobs"]["python-tests"]`, so this quirk is harmless — a wrong traversal would fail Phase 2's Verify immediately.
- **Deleting `requirements.txt` (Phase 3) can only break something that still references it**; Phase 2's `test_workflow_never_mentions_requirements_txt` and Phase 3's full existing-suite run catch any leftover reference.

## Open questions
- **Project name**: `name = "app"` (matches the package directory, PEP 508-valid); uv requires a name to lock, and the spec's assumption says to derive it from the repo/package.
- **Python version**: `requires-python = ">=3.12"`, taken from `ci.yml`'s existing `python-version: "3.12"`; no new constraint invented.
- **`scripts/tests/` in CI**: CI already runs them (in the `python-tests` job via `python -m pytest app/tests scripts/tests`), so they continue to run through `uv run ... pytest`. The separate `tests` job's `python -m unittest discover -s scripts/tests` is left untouched: it does not install from `requirements.txt` (behaviour 5 is satisfied) and it exists to check chart credentials alongside helm and pwsh; converting it is outside this feature's scope.
- **pytest in CI**: obtained ephemerally via `uv run --with pytest pytest ...`, preserving the current mechanism (pytest installed alongside, never a project dependency) and adding no `[dependency-groups]` section, per the spec's assumption.
- **uv on verification machines is not guaranteed**, so Verify blocks use `python -m pytest` with structural lock checks; the real `uv lock --check` runs at build time (Phase 1) and as a CI step (Phase 2). Behaviour 8's clean-checkout proof is the CI run on the pull request itself.

## Hand back
When every phase is built and its Verify block passes:
1. Create `sdlc/features/002-convert-the-project-to-use-the/build-log.md` with one section per phase, in order. Head each one `## Phase <n>: <title>`, then list the files changed, the Verify command you ran and its result, and any deviation from this plan (or "none").
2. Commit it and push it to `feature/002-convert-the-project-to-use-the`.

Commit only this plan's targets and `build-log.md`. Leave every other file alone, including other features' documents under `sdlc/features/`, even for formatting; verification fails on any file outside the targets.

The pipeline waits for this file. Once it has a section for every phase, it verifies the whole branch and opens the pull request.
