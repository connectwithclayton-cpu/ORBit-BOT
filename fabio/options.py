import math

from scipy.stats import norm

from fabio.settings import FabioBacktestSettings


def black_scholes_call(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0:
        return max(S - K, 0.0)
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)


def black_scholes_put(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0:
        return max(K - S, 0.0)
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def option_price(
    direction: str, S: float, T_days: float, cfg: FabioBacktestSettings
) -> float:
    K = round(S)
    T = T_days / 365
    r = 0.05
    iv = cfg.iv_base
    if direction == "CALL":
        return black_scholes_call(S, K, T, r, iv)
    return black_scholes_put(S, K, T, r, iv)
