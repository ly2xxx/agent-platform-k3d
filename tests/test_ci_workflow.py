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
