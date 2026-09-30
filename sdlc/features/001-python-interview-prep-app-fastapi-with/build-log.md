# Build log: 001-python-interview-prep-app-fastapi-with

## Phase 1: Pricing engine and dependency file

**Status:** done · **Files changed:** `requirements.txt`, `app/__init__.py`, `app/pricing.py`, `app/tests/__init__.py`, `app/tests/test_pricing.py`

Added the `app` package with a seeded, NumPy-vectorised Monte Carlo pricer for a European call (`price_european_call`) and the module-level `_price_task((paths, seed))` wrapper that both endpoints will share. `requirements.txt` at the repository root lists fastapi, httpx, numpy and pyyaml; every file is the plan's exact content.

Commands and results (Python 3.12.3, fresh `.venv`):
- `uv pip install -r requirements.txt pytest`: succeeded; `import numpy, yaml, fastapi, httpx` works (numpy 2.5.3, fastapi 0.142.2).
- `python -m pytest app/tests/test_pricing.py -v`: 5 passed.
- `python -m pytest -q`: 5 passed, 10 skipped (the `scripts/tests` suites skip without helm and pwsh).
- `sdlc_stage.py verify --feature 001-python-interview-prep-app-fastapi-with --phase 1 --test-command 'python -m pytest -q'`: **Result: PASSED**, exit 0; scope all inside targets, no frozen files touched, contract matches the approved tag.

Deviations: none.

## Phase 2: Heap-backed order book

**Status:** done · **Files changed:** `app/order_book.py`, `app/tests/test_order_book.py`

Added `OrderBook` with bids in a max-heap (`(-price, seq, order)`) and asks in a min-heap (`(price, seq, order)`), where an `itertools.count()` sequence number breaks price ties first-in-first-out. `best_bid()` and `best_ask()` peek at the heap roots in O(1), and `add()` is O(log n); both files are the plan's exact content.

Commands and results:
- `python -m pytest app/tests/test_order_book.py -v`: 6 passed.
- `python -m pytest -q`: 11 passed, 10 skipped.
- `sdlc_stage.py verify --feature 001-python-interview-prep-app-fastapi-with --phase 2 --test-command 'python -m pytest -q'`: **Result: PASSED**, exit 0 (Phase 1 and Phase 2 Verify blocks and the whole suite passed; scope inside targets; no frozen files touched).

Deviations: none.

## Phase 3: FastAPI app with the two concurrency endpoints

**Status:** done · **Files changed:** `app/main.py`, `app/tests/test_endpoints.py`

Added the FastAPI app with `GET /concurrency/multiprocessing`, a sync endpoint that fans the `runs` copies of `_price_task((paths, seed))` out over a spawn-context `multiprocessing.Pool`, and `GET /concurrency/asyncio`, an async endpoint that `asyncio.gather`s coroutines calling the same blocking task inline on the event loop. Both return a `TimingResponse` with `elapsed_seconds` and the averaged price, so the side-by-side numbers show that asyncio gives no parallelism for CPU-bound work. Both files are the plan's exact content.

Commands and results:
- `python -m pytest app/tests/test_endpoints.py -v`: 10 passed (1 StarletteDeprecationWarning from `fastapi.testclient` about httpx, not a failure).
- Observable check `python -c "from fastapi.testclient import TestClient; from app.main import app; print(TestClient(app).get('/concurrency/asyncio', params={'paths': 500, 'runs': 1, 'seed': 1}).json())"`: printed `{'strategy': 'asyncio', 'elapsed_seconds': 0.00504..., 'option_price': 9.0354..., 'paths_per_run': 500, 'runs': 1, 'seed': 1}`.
- Reverse collection order, `python -m pytest -q scripts/tests app/tests/test_endpoints.py app/tests/test_order_book.py app/tests/test_pricing.py`: 21 passed, 10 skipped (no order dependence, no hung pool workers).
- `sdlc_stage.py verify --feature 001-python-interview-prep-app-fastapi-with --phase 3 --test-command 'python -m pytest -q'`: **Result: PASSED**, exit 0 (Phase 1–3 Verify blocks and the whole suite, 21 passed, 10 skipped; scope inside targets; no frozen files touched).

Deviations: none.

## Phase 4: CI wiring and combined suite

**Status:** done · **Files changed:** `.github/workflows/ci.yml`

Appended the plan's exact `python-tests` job to the end of the `jobs:` mapping in `.github/workflows/ci.yml`. It installs `requirements.txt` plus pytest on Python 3.12 and runs `python -m pytest app/tests scripts/tests`. No existing job or step was changed.

Commands and results:
- The Verify block's YAML assertion printed `ci job ok`.
- `python -m pytest app/tests scripts/tests -q`: 21 passed, 10 skipped (the `scripts/tests` suites skip without helm and pwsh; in CI's `python-tests` job they skip the same way, while the existing `Tests` job still runs them with helm and pwsh).
- `sdlc_stage.py verify --feature 001-python-interview-prep-app-fastapi-with --phase 4 --test-command 'python -m pytest -q'`: **Result: PASSED**, exit 0 (Phase 1–4 Verify blocks and the whole suite; scope inside targets; no frozen files touched).
- Whole-feature preview, `sdlc_stage.py verify --feature 001-python-interview-prep-app-fastapi-with --base main --test-command 'python -m pytest -q'` on the committed branch: **Result: PASSED**, exit 0 (10 files changed since `main`, all inside the plan's targets; contract matches the tag; the whole suite and all four Verify blocks passed).

Deviations: none. Outside the plan, before the run started, `main` got [ly2xxx/agent-platform-k3d#2](https://github.com/ly2xxx/agent-platform-k3d/pull/2), which fixed the SDLC caller workflows' install and test commands. They ran `behave`, which this repository has no features for, and pytest failed to collect `scripts/tests` without PyYAML. The feature branch was created from `main` after that fix, so no merge was needed.
