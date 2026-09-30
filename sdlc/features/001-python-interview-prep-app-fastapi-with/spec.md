<!-- sdlc stage=spec model=glm-5.3:cloud from=intent.md@36f1a5f -->
## Summary

Add a small FastAPI application under a new top-level `app/` package that exposes two REST endpoints running the same CPU-bound Monte Carlo option-pricing task — one via multiprocessing, one via asyncio — each returning timing data so callers can compare them. Alongside it, add a heap-backed order book module. The primary users are engineers preparing for Python interviews; the change is verifiable entirely through automated tests with no network, secrets, or manual steps.

## Behaviour

1. Given the FastAPI app is exercised through FastAPI's `TestClient`, when `GET /concurrency/multiprocessing` is called with no query parameters, then it returns status 200 and a JSON body with `strategy == "multiprocessing"`, `elapsed_seconds` as a positive float, `option_price` as a finite float, and the default `paths_per_run` and `runs` values echoed back.
2. Given the FastAPI app is exercised through `TestClient`, when `GET /concurrency/asyncio` is called with no query parameters, then it returns status 200 and a JSON body with `strategy == "asyncio"`, `elapsed_seconds` as a positive float, `option_price` as a finite float, and the default `paths_per_run` and `runs` values echoed back.
3. Given both endpoints are called with identical query parameters (including the same `seed`), when the responses are compared, then their `option_price` values agree to within a relative tolerance of 1e-6, proving both endpoints execute the same pricing task on the same inputs.
4. Given a request to either endpoint with `paths <= 0` or `runs <= 0`, when the request is made, then the endpoint returns a 422 validation error and does not execute the pricing task.
5. Given an empty `OrderBook`, when `best_bid()` or `best_ask()` is called, then each returns `None`.
6. Given an `OrderBook` with bid orders added at prices 100.0, 100.5, and 99.5 (in that order), when `best_bid()` is called, then it returns the order with price 100.5.
7. Given an `OrderBook` with ask orders added at prices 101.5, 101.0, and 102.0 (in that order), when `best_ask()` is called, then it returns the order with price 101.0.
8. Given an `OrderBook` where two bids share the same best price, when `best_bid()` is called, then it returns the order that was added first.
9. Given the existing test suites under `scripts/tests/` are run unmodified, when they execute in CI, then all of them still pass.

## Interfaces

New top-level package `app/` (proposed module location, since the intent leaves it open):

**`app/pricing.py`** — the shared CPU-bound task used by both endpoints:

```python
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
```

Defaults live in a module constant: `DEFAULT_OPTION_PARAMS: dict[str, float]` with `spot=100.0`, `strike=100.0`, `volatility=0.2`, `risk_free=0.05`, `expiry=1.0`, and `DEFAULT_SEED: int = 42`, `DEFAULT_PATHS_PER_RUN: int = 200_000`, `DEFAULT_RUNS: int = 4`.

**`app/main.py`** — the FastAPI application:

```python
app = FastAPI(title="Python Interview Prep")

class TimingResponse(BaseModel):
    strategy: Literal["multiprocessing", "asyncio"]
    elapsed_seconds: float
    option_price: float
    paths_per_run: int
    runs: int
    seed: int

@app.get("/concurrency/multiprocessing", response_model=TimingResponse)
def run_multiprocessing(
    paths: int = Query(default=DEFAULT_PATHS_PER_RUN, gt=0),
    runs: int = Query(default=DEFAULT_RUNS, gt=0),
    seed: int = Query(default=DEFAULT_SEED),
) -> TimingResponse: ...

@app.get("/concurrency/asyncio", response_model=TimingResponse)
def run_asyncio(
    paths: int = Query(default=DEFAULT_PATHS_PER_RUN, gt=0),
    runs: int = Query(default=DEFAULT_RUNS, gt=0),
    seed: int = Query(default=DEFAULT_SEED),
) -> TimingResponse: ...
```

The multiprocessing endpoint executes `runs` copies of `price_european_call` (each with `paths` paths and the given seed) across worker processes and averages the prices; the asyncio endpoint executes the identical `runs` copies via `asyncio.gather` of coroutines that call the same function, and averages identically. Both measure wall-clock time internally for `elapsed_seconds`.

**`app/order_book.py`** — the heap-backed order book:

```python
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
    def add(self, order: Order) -> None: ...
    def best_bid(self) -> Order | None: ...
    def best_ask(self) -> Order | None: ...
```

Bids are kept in a max-heap (negated prices), asks in a min-heap, with an insertion counter as tie-breaker.

**Tests** — `app/tests/test_endpoints.py` (criteria 1–4, using `fastapi.testclient.TestClient` with small `paths`/`runs` values so they run quickly and offline) and `app/tests/test_order_book.py` (criteria 5–8).

**`.github/workflows/ci.yml`** — add one step running `python -m pytest app/tests scripts/tests` so the new tests execute alongside the existing suite (criterion 9); no existing CI steps are modified.

## Out of scope

- Any UI beyond the two REST endpoints.
- Real-market data, persistence, authentication, or state shared between requests.
- Concurrency strategies other than the two named (no threading, task queues, or async process pools).
- Non-option-pricing Monte Carlo variants; no other data structures.
- Order-book operations beyond add/best-bid/best-ask — in particular no cancel, modify, matching, or trade execution.
- Any guarantee about the *relative* timing between the two endpoints (host-dependent; tests only assert fields are present and positive).
- Deployment to the Kubernetes/Helm platform in this repository; the `k8s/` and `helm/` trees are untouched.

## Open questions

- **Module location:** the intent asks later stages to propose one; assumed a new top-level `app/` package, since the repository has no existing Python application directory.
- **Tie-breaking at equal prices:** not specified; assumed first-added order wins (FIFO), implemented via an insertion counter in the heap entries.
- **Option parameters at the endpoints:** the intent does not say they must be caller-configurable; assumed fixed defaults in `app/pricing.py`, with only `paths`, `runs`, and `seed` exposed as query parameters.
- **Fairness of comparison:** assumed both endpoints perform the identical `runs`-copies-of-`paths`-paths computation with the same seed, differing only in execution strategy.
- **CI wiring:** the intent requires the change to be testable without network access but does not mention CI; assumed a single pytest step is added to `.github/workflows/ci.yml` and nothing else in CI changes.
