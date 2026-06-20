"""Black-Scholes pricing, implied volatility, and greeks.

Databento does not provide pre-computed greeks/IV, so we compute them locally from the
underlying price and option quotes. European Black-Scholes is the baseline; American-style
adjustments can come later if needed for early-exercise-sensitive strategies.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from scipy.stats import norm


def _d1_d2(S: float, K: float, T: float, r: float, sigma: float) -> tuple[float, float]:
    if T <= 0 or sigma <= 0:
        raise ValueError("T and sigma must be positive")
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return d1, d2


def black_scholes_price(
    S: float, K: float, T: float, r: float, sigma: float, kind: str = "call"
) -> float:
    """Price a European option. S=spot, K=strike, T=years to expiry, r=rate, sigma=vol."""
    d1, d2 = _d1_d2(S, K, T, r, sigma)
    if kind == "call":
        return S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    elif kind == "put":
        return K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
    raise ValueError("kind must be 'call' or 'put'")


def implied_volatility(
    price: float, S: float, K: float, T: float, r: float, kind: str = "call",
    tol: float = 1e-6, max_iter: int = 100,
) -> float:
    """Invert Black-Scholes for sigma via bisection (robust, no derivative needed)."""
    lo, hi = 1e-4, 5.0
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        diff = black_scholes_price(S, K, T, r, mid, kind) - price
        if abs(diff) < tol:
            return mid
        if diff > 0:
            hi = mid
        else:
            lo = mid
    return mid


@dataclass
class Greeks:
    delta: float
    gamma: float
    vega: float
    theta: float
    rho: float


def greeks(S: float, K: float, T: float, r: float, sigma: float, kind: str = "call") -> Greeks:
    d1, d2 = _d1_d2(S, K, T, r, sigma)
    pdf = norm.pdf(d1)
    sqrtT = math.sqrt(T)
    if kind == "call":
        delta = norm.cdf(d1)
        theta = (-S * pdf * sigma / (2 * sqrtT) - r * K * math.exp(-r * T) * norm.cdf(d2))
        rho = K * T * math.exp(-r * T) * norm.cdf(d2)
    else:
        delta = norm.cdf(d1) - 1.0
        theta = (-S * pdf * sigma / (2 * sqrtT) + r * K * math.exp(-r * T) * norm.cdf(-d2))
        rho = -K * T * math.exp(-r * T) * norm.cdf(-d2)
    gamma = pdf / (S * sigma * sqrtT)
    vega = S * pdf * sqrtT
    return Greeks(delta=delta, gamma=gamma, vega=vega / 100, theta=theta / 365, rho=rho / 100)
