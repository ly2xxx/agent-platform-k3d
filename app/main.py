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
