import math

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.pricing import DEFAULT_PATHS_PER_RUN, DEFAULT_RUNS, DEFAULT_SEED

@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c

def _assert_timing_body(body: dict, strategy: str) -> None:
    assert body["strategy"] == strategy
    assert isinstance(body["elapsed_seconds"], float) and body["elapsed_seconds"] > 0.0
    assert isinstance(body["option_price"], float) and math.isfinite(body["option_price"])
    assert body["paths_per_run"] > 0
    assert body["runs"] > 0

def test_multiprocessing_endpoint_defaults(client):  # spec behaviour 1
    resp = client.get("/concurrency/multiprocessing")
    assert resp.status_code == 200
    body = resp.json()
    _assert_timing_body(body, "multiprocessing")
    assert body["paths_per_run"] == DEFAULT_PATHS_PER_RUN
    assert body["runs"] == DEFAULT_RUNS
    assert body["seed"] == DEFAULT_SEED

def test_asyncio_endpoint_defaults(client):  # spec behaviour 2
    resp = client.get("/concurrency/asyncio")
    assert resp.status_code == 200
    body = resp.json()
    _assert_timing_body(body, "asyncio")
    assert body["paths_per_run"] == DEFAULT_PATHS_PER_RUN
    assert body["runs"] == DEFAULT_RUNS
    assert body["seed"] == DEFAULT_SEED

def test_same_params_same_price(client):  # spec behaviour 3
    params = {"paths": 2_000, "runs": 2, "seed": 99}
    mp_body = client.get("/concurrency/multiprocessing", params=params).json()
    io_body = client.get("/concurrency/asyncio", params=params).json()
    assert mp_body["option_price"] == pytest.approx(
        io_body["option_price"], rel=1e-6
    )
    assert mp_body["seed"] == io_body["seed"] == 99

@pytest.mark.parametrize("bad", [{"paths": 0}, {"runs": 0}, {"paths": -5, "runs": 2}])
@pytest.mark.parametrize("path", ["/concurrency/multiprocessing", "/concurrency/asyncio"])
def test_invalid_params_rejected(client, path, bad):  # spec behaviour 4
    resp = client.get(path, params=bad)
    assert resp.status_code == 422

def test_custom_params_echoed(client):
    params = {"paths": 1_500, "runs": 3, "seed": 7}
    body = client.get("/concurrency/asyncio", params=params).json()
    assert (body["paths_per_run"], body["runs"], body["seed"]) == (1_500, 3, 7)
