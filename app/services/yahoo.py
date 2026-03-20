"""
WealthLens OSS — Yahoo Finance Service (with cache layer)
"""

import httpx
from typing import Optional
from app.services.cache import get_cached_stock, set_cached_stock, get_cached_fx, set_cached_fx

YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart"
YAHOO_SEARCH = "https://query1.finance.yahoo.com/v1/finance/search"
HEADERS = {"User-Agent": "Mozilla/5.0 WealthLens/2.0"}
DEFAULT_USD_INR = 83.5


async def get_stock_price(ticker: str) -> Optional[dict]:
    # Check cache first
    cached = get_cached_stock(ticker)
    if cached:
        return cached

    try:
        async with httpx.AsyncClient(timeout=10, headers=HEADERS) as client:
            resp = await client.get(f"{YAHOO_CHART}/{ticker}", params={"interval": "1d"})
            resp.raise_for_status()
            data = resp.json()

        result = data.get("chart", {}).get("result", [])
        if not result:
            return None

        meta = result[0].get("meta", {})
        price_data = {
            "symbol": ticker,
            "name": meta.get("shortName", meta.get("longName", ticker)),
            "price": meta.get("regularMarketPrice", 0),
            "currency": meta.get("currency", "INR"),
        }
        set_cached_stock(ticker, price_data)
        return price_data
    except Exception:
        return None


async def search_etf(query: str) -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=10, headers=HEADERS) as client:
            resp = await client.get(YAHOO_SEARCH, params={"q": query})
            resp.raise_for_status()
            data = resp.json()

        return [
            {"symbol": item.get("symbol", ""), "name": item.get("shortname", item.get("longname", "")),
             "exchange": item.get("exchange", ""), "type": item.get("quoteType", "")}
            for item in data.get("quotes", [])
        ]
    except Exception:
        return []


async def get_usd_inr_rate() -> float:
    # Check cache
    cached = get_cached_fx()
    if cached:
        return cached

    try:
        async with httpx.AsyncClient(timeout=10, headers=HEADERS) as client:
            resp = await client.get(f"{YAHOO_CHART}/USDINR=X", params={"interval": "1d"})
            resp.raise_for_status()
            data = resp.json()

        result = data.get("chart", {}).get("result", [])
        rate = result[0].get("meta", {}).get("regularMarketPrice", DEFAULT_USD_INR) if result else DEFAULT_USD_INR
        set_cached_fx(rate)
        return rate
    except Exception:
        return DEFAULT_USD_INR
