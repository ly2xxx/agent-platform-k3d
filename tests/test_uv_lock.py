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
