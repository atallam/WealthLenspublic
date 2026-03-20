"""
WealthLens OSS — Stock/ETF Price Service (multi-source)

Fallback chain:
  1. Twelve Data  — proper API with SLA, free 800/day, covers NSE/BSE/US
  2. Yahoo Finance — unofficial, no SLA, but wide coverage
  3. Manual entry  — user provides price directly

For Indian stocks: ticker = RELIANCE, exchange = NSE
For US stocks: ticker = AAPL, no exchange needed
"""

import httpx
from typing import Optional
from app.services.cache import get_cached_stock, set_cached_stock

YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart"
YAHOO_SEARCH = "https://query1.finance.yahoo.com/v1/finance/search"
YAHOO_HEADERS = {"User-Agent": "Mozilla/5.0 WealthLens/2.0"}


async def get_price(ticker: str, exchange: str = "", country: str = "IN") -> Optional[dict]:
    """
    Get stock/ETF price with Twelve Data → Yahoo fallback.
    For Indian: pass exchange="NSE" or append .NS to ticker for Yahoo.
    """
    cache_key = f"stock:{ticker}:{exchange}"
    cached = get_cached_stock(cache_key)
    if cached:
        return cached

    # Source 1: Twelve Data
    from app.services.twelvedata import get_stock_price as td_price
    result = await td_price(ticker, exchange)
    if result and result.get("price"):
        set_cached_stock(cache_key, result)
        return result

    # Source 2: Yahoo Finance
    result = await _yahoo_price(ticker, exchange)
    if result and result.get("price"):
        set_cached_stock(cache_key, result)
        return result

    return None


async def _yahoo_price(ticker: str, exchange: str = "") -> Optional[dict]:
    """Yahoo Finance fallback."""
    # Build Yahoo symbol
    if exchange == "NSE":
        symbol = f"{ticker}.NS" if not ticker.endswith((".NS", ".BO")) else ticker
    elif exchange == "BSE":
        symbol = f"{ticker}.BO" if not ticker.endswith((".NS", ".BO")) else ticker
    else:
        symbol = ticker  # US stocks: use as-is

    try:
        async with httpx.AsyncClient(timeout=10, headers=YAHOO_HEADERS) as client:
            resp = await client.get(f"{YAHOO_CHART}/{symbol}", params={"interval": "1d"})
            resp.raise_for_status()
            data = resp.json()

        result = data.get("chart", {}).get("result", [])
        if not result:
            return None

        meta = result[0].get("meta", {})
        return {
            "symbol": ticker,
            "name": meta.get("shortName", meta.get("longName", ticker)),
            "price": meta.get("regularMarketPrice", 0),
            "currency": meta.get("currency", "INR"),
            "exchange": exchange or meta.get("exchangeName", ""),
            "source": "yahoo",
        }
    except Exception:
        return None


async def search(query: str) -> list[dict]:
    """Search stocks — Twelve Data → Yahoo fallback."""
    # Source 1: Twelve Data
    from app.services.twelvedata import search_stocks as td_search
    results = await td_search(query)
    if results:
        return results

    # Source 2: Yahoo Finance
    try:
        async with httpx.AsyncClient(timeout=10, headers=YAHOO_HEADERS) as client:
            resp = await client.get(YAHOO_SEARCH, params={"q": query})
            resp.raise_for_status()
            data = resp.json()

        return [
            {"symbol": item.get("symbol", ""), "name": item.get("shortname", item.get("longname", "")),
             "exchange": item.get("exchange", ""), "type": item.get("quoteType", ""),
             "source": "yahoo"}
            for item in data.get("quotes", [])
        ]
    except Exception:
        return []
