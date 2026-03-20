"""
WealthLens OSS — FX Rate Service (multi-source)

Fallback chain:
  1. exchangerate-api.com (free: 1500/month, reliable, no key needed for open endpoint)
  2. Twelve Data (if configured)
  3. Yahoo Finance (unofficial)
  4. Hardcoded fallback (83.5)
"""

import httpx
from typing import Optional
from app.services.cache import get_cached_fx, set_cached_fx

DEFAULT_USD_INR = 83.5


async def get_usd_inr() -> float:
    """Get USD/INR rate with multi-source fallback."""
    # Check cache first
    cached = get_cached_fx()
    if cached:
        return cached

    rate = None

    # Source 1: exchangerate-api.com (free, no key needed for open endpoint)
    rate = await _from_exchangerate_api()
    if rate and rate > 50:  # Sanity check
        set_cached_fx(rate)
        return rate

    # Source 2: Twelve Data
    from app.services.twelvedata import get_forex_rate
    rate_td = await get_forex_rate("USD", "INR")
    if rate_td and rate_td > 50:
        set_cached_fx(rate_td)
        return rate_td

    # Source 3: Yahoo Finance
    rate_yf = await _from_yahoo()
    if rate_yf and rate_yf > 50:
        set_cached_fx(rate_yf)
        return rate_yf

    # Source 4: Hardcoded
    return DEFAULT_USD_INR


async def _from_exchangerate_api() -> Optional[float]:
    """Free endpoint: https://open.er-api.com/v6/latest/USD"""
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get("https://open.er-api.com/v6/latest/USD")
            resp.raise_for_status()
            data = resp.json()
        if data.get("result") == "success":
            return float(data.get("rates", {}).get("INR", 0))
    except Exception:
        pass
    return None


async def _from_yahoo() -> Optional[float]:
    """Yahoo Finance USDINR=X"""
    try:
        async with httpx.AsyncClient(timeout=8, headers={
            "User-Agent": "Mozilla/5.0 WealthLens/2.0"
        }) as client:
            resp = await client.get(
                "https://query1.finance.yahoo.com/v8/finance/chart/USDINR=X",
                params={"interval": "1d"}
            )
            resp.raise_for_status()
            data = resp.json()
        result = data.get("chart", {}).get("result", [])
        if result:
            return float(result[0].get("meta", {}).get("regularMarketPrice", 0))
    except Exception:
        pass
    return None
