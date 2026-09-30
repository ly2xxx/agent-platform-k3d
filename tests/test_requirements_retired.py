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
