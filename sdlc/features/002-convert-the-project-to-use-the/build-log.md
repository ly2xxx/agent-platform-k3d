# Build log: 002-convert-the-project-to-use-the

Built against the second approved plan (tag `sdlc/002-convert-the-project-to-use-the/approved` moved by issue ly2xxx/agent-platform-k3d#11). The first plan couldn't pass: its Phase 4 guard test failed whenever any file outside `sdlc/` mentioned `requirements.txt`, and the test file itself did. Nothing from that plan was built.

## Phase 1: pyproject.toml and uv.lock

**Status:** done · **Files changed:** `pyproject.toml`, `uv.lock`, `tests/test_uv_lock.py`

Added a root `pyproject.toml` whose only table is `[project]` (name `app`, `requires-python = ">=3.12"`, and the four former `requirements.txt` dependencies with unchanged lower bounds), and generated `uv.lock` with `uv lock`. With no `[build-system]`, uv locks the root as a virtual project (`source = { virtual = "." }`) and pins 18 packages. `tests/test_uv_lock.py` is the plan's exact content.

Commands and results (uv 0.8.17, Python 3.12.3):
- `uv lock`: wrote `uv.lock` (18 packages).
- `uv lock --check`: exit 0 ("Resolved 18 packages").
- `python -m pytest tests/test_uv_lock.py -v`: 6 passed.
- `python -m pytest app/tests -q`: 21 passed.
- `sdlc_stage.py verify --feature 002-convert-the-project-to-use-the --phase 1 --test-command 'python -m pytest -q'`: **Result: PASSED**, exit 0 (whole suite 27 passed, 10 skipped; scope inside targets; no frozen files touched).

Deviations: none.

## Phase 2: CI through uv and `.venv` ignored

**Status:** done · **Files changed:** `.github/workflows/ci.yml`, `.gitignore`, `tests/test_ci_workflow.py`

Replaced only the `python-tests` job in `ci.yml` with the plan's exact job. It sets up uv and Python 3.12 with `astral-sh/setup-uv@v5`, runs `uv lock --check` then `uv sync`, and runs both suites with `uv run --with pytest pytest app/tests scripts/tests`; the `chart`, `tests` and `secrets` jobs are untouched. Appended `.venv/` to `.gitignore`, and `tests/test_ci_workflow.py` is the plan's exact content.

Commands and results:
- `python -m pytest tests/test_ci_workflow.py -v`: 7 passed.
- `python -m pytest app/tests -q`: 21 passed.
- `test -z "$(grep -n requirements.txt .github/workflows/ci.yml || true)"`: exit 0.
- `sdlc_stage.py verify --feature 002-convert-the-project-to-use-the --phase 2 --test-command 'python -m pytest -q'`: **Result: PASSED**, exit 0 (Phase 1 and 2 Verify blocks and the whole suite, 34 passed, 10 skipped; scope inside targets; no frozen files touched).
- Before building, I ran the new job's commands in a scratch copy of the finished plan: `uv lock --check` exit 0, `uv sync` exit 0, and `uv run --with pytest pytest app/tests scripts/tests` gave 21 passed, 10 skipped.

Deviations: none.

## Phase 3: Retire requirements.txt

**Status:** done · **Files changed:** `requirements.txt` (deleted), `tests/test_requirements_retired.py`

Deleted `requirements.txt`, so `pyproject.toml` and `uv.lock` are now the only record of the dependencies. `tests/test_requirements_retired.py` is the plan's exact content and proves the file is gone while all four dependencies remain declared and locked.

Commands and results:
- `python -m pytest tests/test_requirements_retired.py -v`: 3 passed.
- `python -m pytest app/tests scripts/tests -q`: passed.
- `test ! -e requirements.txt`: exit 0.
- `sdlc_stage.py verify --feature 002-convert-the-project-to-use-the --phase 3 --test-command 'python -m pytest -q'`: **Result: PASSED**, exit 0 (Phase 1–3 Verify blocks and the whole suite, 37 passed, 10 skipped; scope inside targets; no frozen files touched).
- Whole-feature preview, `sdlc_stage.py verify --feature 002-convert-the-project-to-use-the --base main --test-command 'python -m pytest -q'` on the committed branch: **Result: PASSED**, exit 0 (8 files changed since `main`, all inside the plan's targets; contract matches the tag; the whole suite and all three Verify blocks passed).

Deviations: none. Outside the plan, before this run, `main` got ly2xxx/agent-platform-k3d#9, which made the SDLC caller workflows install a `uv.lock` project (`uv sync --locked`). The run's install command is fixed from `main` when the run starts, so without it the final verify would have found no dependencies once `requirements.txt` was deleted.
