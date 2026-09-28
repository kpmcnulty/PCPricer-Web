"""Shared HTTP, curve-fitting and validation helpers.

Every problem raises ScrapeError. Nothing here falls back to old data: a run
either produces a complete, validated data.json or it fails.
"""
import random
import time

import numpy as np
import requests
from scipy import optimize

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

# Seconds to wait between requests so we don't hammer the sites. Tests set this to (0, 0).
DELAY = (5, 15)


class ScrapeError(RuntimeError):
    pass


def session():
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
    return s


def get(s, url, **kwargs):
    try:
        r = s.get(url, timeout=60, **kwargs)
    except requests.RequestException as e:
        raise ScrapeError(f"{url}: {e}") from e
    if r.status_code != 200:
        raise ScrapeError(f"{url}: HTTP {r.status_code}")
    time.sleep(random.uniform(*DELAY))
    return r


# Curve formulas. Each one must match the function of the same name in script.js.

def poly(x, a, b, c, d):
    return a * x**4 + b * x**3 + c * x**2 + d * x


def ypoly(x, a, b, c, d):
    return a * x**3 + b * x**2 + c * x + d


def ln(x, a, b, c):
    return a * np.log(b * x + 1) + c * x


def linear(x, a, b):
    return a * x + b


def fit(func, xs, ys, name, **kwargs):
    """Fit func to (xs, ys) and check the result actually describes the data."""
    xs = np.asarray(xs, dtype=float)
    ys = np.asarray(ys, dtype=float)
    n_params = func.__code__.co_argcount - 1
    if len(xs) < n_params + 1:
        raise ScrapeError(f"{name}: only {len(xs)} data points, need at least {n_params + 1}")
    try:
        params, _ = optimize.curve_fit(func, xs, ys, maxfev=20000, **kwargs)
    except (RuntimeError, ValueError) as e:
        raise ScrapeError(f"{name}: curve fit failed: {e}") from e
    if not np.all(np.isfinite(params)):
        raise ScrapeError(f"{name}: curve fit produced non-finite parameters {params}")

    predicted = func(xs, *params)
    if np.any(predicted <= 0):
        raise ScrapeError(f"{name}: fitted curve predicts non-positive prices")
    median_error = float(np.median(np.abs(predicted - ys) / ys))
    if median_error > 0.5:
        raise ScrapeError(f"{name}: fitted curve is off by a median {median_error:.0%} from the data")
    print(f"  {name}: {len(xs)} points, median error {median_error:.0%}")
    return [float(p) for p in params]
