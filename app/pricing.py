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
