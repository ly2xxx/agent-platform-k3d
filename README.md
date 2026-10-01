# Python Interview Prep App

A FastAPI application comparing CPU-bound task execution between **multiprocessing** and **asyncio** using a Monte Carlo European call option pricing simulation.

## Prerequisites

- Python `>= 3.12`
- [`uv`](https://docs.astral.sh/uv/) (recommended) or `pip`

## Quick Start

### Using `uv` (Recommended)

1. **Install dependencies:**

   ```bash
   uv sync
   ```
2. **Run the development server:**

   ```bash
   uv run --with uvicorn uvicorn app.main:app --reload
   ```

The application will start at `http://127.0.0.1:8000`.

---

### Using standard `venv` & `pip`

1. **Create and activate a virtual environment:**

   ```bash
   # Windows (PowerShell)
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1

   # Linux / macOS
   python -m venv .venv
   source .venv/bin/activate
   ```
2. **Install dependencies:**

   ```bash
   pip install -e . uvicorn
   ```
3. **Run the application:**

   ```bash
   uvicorn app.main:app --reload
   ```

---

## API Endpoints

| Endpoint                         | Method  | Description                                        |
| :------------------------------- | :------ | :------------------------------------------------- |
| `/concurrency/multiprocessing` | `GET` | Computes option prices across CPU worker processes |
| `/concurrency/asyncio`         | `GET` | Runs pricing tasks sequentially on the event loop  |
| `/docs`                        | `GET` | Interactive Swagger UI documentation               |
| `/redoc`                       | `GET` | ReDoc API documentation                            |

### Query Parameters

- `paths` *(int, default: 200000)*: Monte Carlo paths simulated per run.
- `runs` *(int, default: 4)*: Number of simulation runs.
- `seed` *(int, default: 42)*: Random seed for deterministic output.

### Example Requests

```bash
# Test multiprocessing execution
curl "http://127.0.0.1:8000/concurrency/multiprocessing?paths=200000&runs=4"

# Test asyncio execution
curl "http://127.0.0.1:8000/concurrency/asyncio?paths=200000&runs=4"
```

---

## Running Tests

Run the test suite using `uv`:

```bash
uv run --with pytest pytest app/tests
```
