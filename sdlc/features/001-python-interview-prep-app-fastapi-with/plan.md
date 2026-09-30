<!-- sdlc stage=plan model=glm-5.3:cloud from=intent.md,spec.md@97626d1 -->
## Approach
Add a new top-level `app/` Python package containing three modules — a shared NumPy-based Monte Carlo pricer (`app/pricing.py`), a heap-backed order book (`app/order_book.py`), and a FastAPI app (`app/main.py`) with two endpoints that run the identical pricing workload via a multiprocessing pool and via `asyncio.gather` respectively — plus a `requirements.txt` (the repo has no Python dependency file) and one additive CI job that runs the new and existing test suites together. Everything is verified in-process with pytest and FastAPI's `TestClient`; no servers, network, or secrets are needed.

## Coverage

| Done when (intent.md) | Spec behaviours | Phase |
| :-- | :-- | :-- |
| A FastAPI app exists with two REST endpoints that both execute the same Monte Carlo option-pricing task. | 1, 2, 3 | Phase 3 |
| One endpoint performs the task via multiprocessing, the other via asyncio. | 1, 2 | Phase 3 |
| Each endpoint returns timing information sufficient to compare the two approaches side by side. | 1, 2 | Phase 3 |
| A separate module implements an order book using a heap as its core structure. | 5, 6, 7, 8 | Phase 2 |
| The existing tests still pass. | 9 (plus 4: validation is Phase 3) | Phase 4 (and every phase's Verify keeps the tree green; the shared suite check is Phase 4) |

## Phase 1: Pricing engine and dependency file
<!-- phase: 1 -->
<!-- targets: requirements.txt, app/__init__.py, app/pricing.py, app/tests/__init__.py, app/tests/test_pricing.py -->
<!-- frozen: scripts/tests/test_chart_credentials.py, scripts/tests/test_new_dev_secrets.py, .github/workflows/ci.yml, .gitignore -->

**Goal:** A pure-Python package `app` contains a deterministic, seeded Monte Carlo call pricer, installable from `requirements.txt`, proven by tests that pass without network access.

**Changes:**
- `requirements.txt` (new, repository root):
  ```text
  fastapi>=0.110
  httpx>=0.27
  numpy>=1.26
  pyyaml>=6.0
  ```
  (`fastapi`/`httpx` are needed in Phase 3, `numpy` for the vectorised pricer, `pyyaml` so the pre-existing `scripts/tests/` suite can run in the verification virtualenv and for the Phase 4 CI-file check.)
- `app/__init__.py` (new): empty file (makes `app` an importable package, required for multiprocessing spawn workers in Phase 3).
- `app/tests/__init__.py` (new): empty file.
- `app/pricing.py` (new), exact contents:
  ```python
  """Shared CPU-bound Monte Carlo task used by both concurrency endpoints."""
  import numpy as np

  DEFAULT_OPTION_PARAMS: dict[str, float] = {
      "spot": 100.0,
      "strike": 100.0,
      "volatility": 0.2,
      "risk_free": 0.05,
      "expiry": 1.0,
  }
  DEFAULT_SEED: int = 42
  DEFAULT_PATHS_PER_RUN: int = 200_000
  DEFAULT_RUNS: int = 4

  def price_european_call(
      spot: float,
      strike: float,
      volatility: float,
      risk_free: float,
      expiry: float,
      paths: int,
      seed: int,
  ) -> float:
      """Monte Carlo estimate of a European call option price. Deterministic for a given seed."""
      rng = np.random.default_rng(seed)
      z = rng.standard_normal(paths)
      st = spot * np.exp(
          (risk_free - 0.5 * volatility**2) * expiry
          + volatility * np.sqrt(expiry) * z
      )
      payoffs = np.maximum(st - strike, 0.0)
      return float(np.exp(-risk_free * expiry) * payoffs.mean())

  def _price_task(task: tuple[int, int]) -> float:
      """One unit of work for the endpoints: price with default option params.

      `task` is `(paths, seed)`. Kept module-level so multiprocessing spawn
      workers can import it.
      """
      paths, seed = task
      return price_european_call(**DEFAULT_OPTION_PARAMS, paths=paths, seed=seed)
  ```
- `app/tests/test_pricing.py` (new):
  ```python
  import math

  from app.pricing import (
      DEFAULT_OPTION_PARAMS,
      DEFAULT_PATHS_PER_RUN,
      DEFAULT_RUNS,
      DEFAULT_SEED,
      _price_task,
      price_european_call,
  )

  def _price(paths: int, seed: int) -> float:
      return price_european_call(**DEFAULT_OPTION_PARAMS, paths=paths, seed=seed)

  def test_deterministic_for_same_seed():
      a = _price(paths=20_000, seed=7)
      b = _price(paths=20_000, seed=7)
      assert a == b

  def test_seed_changes_result():
      a = _price(paths=20_000, seed=7)
      b = _price(paths=20_000, seed=8)
      assert a != b

  def test_returns_finite_float_close_to_black_scholes():
      price = _price(paths=200_000, seed=DEFAULT_SEED)
      assert isinstance(price, float)
      assert math.isfinite(price)
      # Black-Scholes value for these params is ~10.45; loose tolerance for MC error.
      assert abs(price - 10.4506) < 1.0

  def test_price_task_matches_price_european_call():
      assert _price_task((5_000, 123)) == _price(paths=5_000, seed=123)

  def test_default_constants():
      assert DEFAULT_PATHS_PER_RUN == 200_000
      assert DEFAULT_RUNS == 4
      assert DEFAULT_SEED == 42
      assert DEFAULT_OPTION_PARAMS == {
          "spot": 100.0, "strike": 100.0, "volatility": 0.2,
          "risk_free": 0.05, "expiry": 1.0,
      }
  ```

**Definition of done:**
- [ ] `app/tests/test_pricing.py::test_deterministic_for_same_seed` proves the seed makes the task reproducible (required for spec behaviour 3).
- [ ] `app/tests/test_pricing.py::test_returns_finite_float_close_to_black_scholes` proves the task is a real, finite option price (spec behaviours 1–2 require `option_price` finite).
- [ ] `app/tests/test_pricing.py::test_price_task_matches_price_european_call` proves `_price_task` is exactly the shared task both endpoints will call.
- [ ] `pip install -r requirements.txt` succeeds and provides `numpy` and `yaml` importable in the test environment.

**Verify:**
```bash
python -m pytest app/tests/test_pricing.py -v
```

**Attempt budget:** 3 failed attempts, then stop and revise this plan instead of retrying.

## Phase 2: Heap-backed order book
<!-- phase: 2 -->
<!-- targets: app/order_book.py, app/tests/test_order_book.py -->
<!-- frozen: app/pricing.py, app/tests/test_pricing.py, scripts/tests/test_chart_credentials.py, scripts/tests/test_new_dev_secrets.py -->

**Goal:** `app.order_book.OrderBook` returns the highest bid and lowest ask, first-added winning ties, backed by two heaps, per spec behaviours 5–8.

**Changes:**
- `app/order_book.py` (new), exact contents:
  ```python
  """Heap-backed order book: bids in a max-heap, asks in a min-heap."""
  import heapq
  import itertools
  from dataclasses import dataclass
  from enum import Enum

  class Side(str, Enum):
      BID = "bid"
      ASK = "ask"

  @dataclass(frozen=True)
  class Order:
      order_id: str
      side: Side
      price: float
      quantity: int

  class OrderBook:
      def __init__(self) -> None:
          # Entries: bids (-price, seq, order) -> max-heap by price, FIFO on ties.
          # Entries: asks (price, seq, order) -> min-heap by price, FIFO on ties.
          self._bids: list[tuple[float, int, Order]] = []
          self._asks: list[tuple[float, int, Order]] = []
          self._counter = itertools.count()

      def add(self, order: Order) -> None:
          seq = next(self._counter)
          if order.side is Side.BID:
              heapq.heappush(self._bids, (-order.price, seq, order))
          else:
              heapq.heappush(self._asks, (order.price, seq, order))

      def best_bid(self) -> Order | None:
          return self._bids[0][2] if self._bids else None

      def best_ask(self) -> Order | None:
          return self._asks[0][2] if self._asks else None
  ```
- `app/tests/test_order_book.py` (new), exact contents:
  ```python
  from app.order_book import Order, OrderBook, Side

  def _bid(order_id: str, price: float, qty: int = 10) -> Order:
      return Order(order_id=order_id, side=Side.BID, price=price, quantity=qty)

  def _ask(order_id: str, price: float, qty: int = 10) -> Order:
      return Order(order_id=order_id, side=Side.ASK, price=price, quantity=qty)

  def test_empty_book_returns_none():  # spec behaviour 5
      book = OrderBook()
      assert book.best_bid() is None
      assert book.best_ask() is None

  def test_best_bid_is_highest_price():  # spec behaviour 6
      book = OrderBook()
      for price in (100.0, 100.5, 99.5):
          book.add(_bid(f"b{price}", price))
      assert book.best_bid() is not None
      assert book.best_bid().price == 100.5

  def test_best_ask_is_lowest_price():  # spec behaviour 7
      book = OrderBook()
      for price in (101.5, 101.0, 102.0):
          book.add(_ask(f"a{price}", price))
      assert book.best_ask() is not None
      assert book.best_ask().price == 101.0

  def test_tie_at_best_bid_returns_first_added():  # spec behaviour 8
      book = OrderBook()
      book.add(_bid("first", 100.5))
      book.add(_bid("second", 100.5))
      assert book.best_bid() is not None
      assert book.best_bid().order_id == "first"

  def test_tie_at_best_ask_returns_first_added():
      book = OrderBook()
      book.add(_ask("first", 101.0))
      book.add(_ask("second", 101.0))
      assert book.best_ask() is not None
      assert book.best_ask().order_id == "first"

  def test_sides_are_independent():
      book = OrderBook()
      book.add(_bid("b", 99.0))
      book.add(_ask("a", 101.0))
      assert book.best_bid().price == 99.0
      assert book.best_ask().price == 101.0
  ```

**Definition of done:**
- [ ] `app/tests/test_order_book.py::test_empty_book_returns_none` proves spec behaviour 5.
- [ ] `app/tests/test_order_book.py::test_best_bid_is_highest_price` proves spec behaviour 6.
- [ ] `app/tests/test_order_book.py::test_best_ask_is_lowest_price` proves spec behaviour 7.
- [ ] `app/tests/test_order_book.py::test_tie_at_best_bid_returns_first_added` proves spec behaviour 8.

**Verify:**
```bash
python -m pytest app/tests/test_order_book.py -v
```

**Attempt budget:** 3 failed attempts, then stop and revise this plan instead of retrying.

## Phase 3: FastAPI app with the two concurrency endpoints
<!-- phase: 3 -->
<!-- targets: app/main.py, app/tests/test_endpoints.py -->
<!-- frozen: app/pricing.py, app/order_book.py, app/tests/test_pricing.py, app/tests/test_order_book.py, scripts/tests/test_chart_credentials.py, scripts/tests/test_new_dev_secrets.py -->

**Goal:** `GET /concurrency/multiprocessing` and `GET /concurrency/asyncio` both run the identical seeded pricing workload and return comparable timing bodies per spec behaviours 1–4.

**Changes:**
- `app/main.py` (new), exact contents:
  ```python
  """FastAPI app comparing multiprocessing vs asyncio on one CPU-bound task."""
  import asyncio
  import multiprocessing as mp
  import time
  from typing import Literal

  from fastapi import FastAPI, Query
  from pydantic import BaseModel

  from app.pricing import (
      DEFAULT_PATHS_PER_RUN,
      DEFAULT_RUNS,
      DEFAULT_SEED,
      _price_task,
  )

  app = FastAPI(title="Python Interview Prep")

  class TimingResponse(BaseModel):
      strategy: Literal["multiprocessing", "asyncio"]
      elapsed_seconds: float
      option_price: float
      paths_per_run: int
      runs: int
      seed: int

  async def _price_coro(task: tuple[int, int]) -> float:
      """Async wrapper that calls the same blocking task inline (no parallelism)."""
      return _price_task(task)

  @app.get("/concurrency/multiprocessing", response_model=TimingResponse)
  def run_multiprocessing(
      paths: int = Query(default=DEFAULT_PATHS_PER_RUN, gt=0),
      runs: int = Query(default=DEFAULT_RUNS, gt=0),
      seed: int = Query(default=DEFAULT_SEED),
  ) -> TimingResponse:
      tasks = [(paths, seed)] * runs
      start = time.perf_counter()
      ctx = mp.get_context("spawn")
      with ctx.Pool(processes=runs) as pool:
          prices = pool.map(_price_task, tasks)
      elapsed = time.perf_counter() - start
      return TimingResponse(
          strategy="multiprocessing",
          elapsed_seconds=elapsed,
          option_price=sum(prices) / len(prices),
          paths_per_run=paths,
          runs=runs,
          seed=seed,
      )

  @app.get("/concurrency/asyncio", response_model=TimingResponse)
  async def run_asyncio(
      paths: int = Query(default=DEFAULT_PATHS_PER_RUN, gt=0),
      runs: int = Query(default=DEFAULT_RUNS, gt=0),
      seed: int = Query(default=DEFAULT_SEED),
  ) -> TimingResponse:
      tasks = [(paths, seed)] * runs
      start = time.perf_counter()
      prices = await asyncio.gather(*(_price_coro(t) for t in tasks))
      elapsed = time.perf_counter() - start
      return TimingResponse(
          strategy="asyncio",
          elapsed_seconds=elapsed,
          option_price=sum(prices) / len(prices),
          paths_per_run=paths,
          runs=runs,
          seed=seed,
      )
  ```
  Both endpoints execute the identical `runs` copies of `_price_task((paths, seed))` and average identically, so with the same seed their `option_price` values match exactly (spec behaviour 3).
- `app/tests/test_endpoints.py` (new), exact contents:
  ```python
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
  ```
  All tests use `TestClient` in-process; the `client` fixture's context manager shuts down the app (and any TestClient-owned event loop) on teardown, and the multiprocessing `Pool` is closed by its `with` block inside the endpoint, so no background processes survive a test.

**Definition of done:**
- [ ] `app/tests/test_endpoints.py::test_multiprocessing_endpoint_defaults` proves spec behaviour 1 (200, correct fields, defaults echoed).
- [ ] `app/tests/test_endpoints.py::test_asyncio_endpoint_defaults` proves spec behaviour 2.
- [ ] `app/tests/test_endpoints.py::test_same_params_same_price` proves spec behaviour 3 (identical inputs → prices agree within 1e-6 relative).
- [ ] `app/tests/test_endpoints.py::test_invalid_params_rejected` proves spec behaviour 4 (422 for `paths <= 0` or `runs <= 0`).
- [ ] Observable check: `python -c "from fastapi.testclient import TestClient; from app.main import app; print(TestClient(app).get('/concurrency/asyncio', params={'paths': 500, 'runs': 1, 'seed': 1}).json())"` prints a body with `strategy == "asyncio"` and positive `elapsed_seconds`.

**Verify:**
```bash
python -m pytest app/tests/test_endpoints.py -v
```

**Attempt budget:** 3 failed attempts, then stop and revise this plan instead of retrying.

## Phase 4: CI wiring and combined suite
<!-- phase: 4 -->
<!-- targets: .github/workflows/ci.yml -->
<!-- frozen: app/pricing.py, app/order_book.py, app/main.py, app/tests/test_pricing.py, app/tests/test_order_book.py, app/tests/test_endpoints.py, scripts/tests/test_chart_credentials.py, scripts/tests/test_new_dev_secrets.py -->

**Goal:** `.github/workflows/ci.yml` gains one additive job that runs `python -m pytest app/tests scripts/tests`, and the new and existing suites pass together in one pytest invocation (spec behaviour 9).

**Changes:**
- `.github/workflows/ci.yml`: append one new top-level job under the existing `jobs:` mapping, modifying nothing already present. Exact block to add (same indentation as existing job keys under `jobs:`):
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
  If the file has no `jobs:` key at all (not expected), add the standard `jobs:` mapping containing exactly this job.

**Definition of done:**
- [ ] A single pytest run over both trees collects and passes all tests from `app/tests/` and the unmodified `scripts/tests/`, proving spec behaviour 9 and intent item "existing tests still pass".
- [ ] The CI file check confirms the new job exists with the pytest step as its last step, and nothing else in the workflow was touched: `git diff --stat sdlc/001-python-interview-prep-app-fastapi-with/approved` shows no file outside this plan's targets across the whole build (checked at final verification).

**Verify:**
```bash
python -c "import yaml; d = yaml.safe_load(open('.github/workflows/ci.yml')); assert 'python-tests' in d['jobs'], 'job missing'; assert d['jobs']['python-tests']['steps'][-1]['run'] == 'python -m pytest app/tests scripts/tests', 'pytest step missing'; print('ci job ok')"
python -m pytest app/tests scripts/tests -q
```

**Attempt budget:** 3 failed attempts, then stop and revise this plan instead of retrying.

## Risks
- **Spawn-context multiprocessing under pytest** (Phase 3): on some platforms `fork`-based pools can hang in test runners; the plan pins `mp.get_context("spawn")` and a module-level `_price_task`, which is import-safe. Phase 3's Verify (all endpoint tests in one process) catches any hang immediately.
- **Slow default-parameter tests** (Phase 3): defaults are 200,000 paths × 4 runs; NumPy makes each run milliseconds, but the spawn pool adds ~1–2 s overhead — acceptable. If Verify times out, reduce nothing; revise the plan (attempt budget).
- **Existing `scripts/tests/` may depend on libraries not in `requirements.txt`** (Phase 4): assumed they need only `pytest` and `pyyaml` (both provided). If the combined Verify fails on an import, that is caught in Phase 4 and the dependency must be added to `requirements.txt` before proceeding.
- **`pydantic`/`fastapi` version drift** (Phase 3): `Literal` and `Query(gt=...)` are stable across pinned minimums; any incompatibility surfaces in Phase 3's Verify.
- **CI YAML structure unknown** (Phase 4): the additive top-level job avoids touching existing steps; the Phase 4 YAML assertion fails loudly if the append was placed wrong.

## Open questions
- **`pyyaml` in `requirements.txt`:** the pre-existing `scripts/tests/` suite is assumed to parse YAML chart files; `pyyaml` is included so the verification virtualenv can run it and so Phase 4's CI-file check works. If CI already installs it, this is harmless duplication.
- **Repository has no Python dependency file** (no `pyproject.toml`), so per the pipeline rules `requirements.txt` is created at the root in Phase 1 and is a Phase 1 target.
- **CI file structure:** the existing `.github/workflows/ci.yml` is assumed to have a top-level `jobs:` mapping; the change is strictly additive. If it does not, the Phase 4 Verify assertion fails and the plan is revised rather than existing steps modified.
- All spec assumptions (module location `app/`, FIFO tie-breaking, fixed option parameters, identical workloads per endpoint) are carried through unchanged from `spec.md`.

## Hand back
When every phase is built and its Verify block passes:
1. Create `sdlc/features/001-python-interview-prep-app-fastapi-with/build-log.md` with one section per phase, in order. Head each one `## Phase <n>: <title>`, then list the files changed, the Verify command you ran and its result, and any deviation from this plan (or "none").
2. Commit it and push it to `feature/001-python-interview-prep-app-fastapi-with`.

Commit only this plan's targets and `build-log.md`. Leave every other file alone, including other features' documents under `sdlc/features/`, even for formatting; verification fails on any file outside the targets.

The pipeline waits for this file. Once it has a section for every phase, it verifies the whole branch and opens the pull request.
