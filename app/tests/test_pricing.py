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
