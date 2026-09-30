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
