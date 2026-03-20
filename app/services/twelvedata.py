"""
WealthLens OSS — Twelve Data Service (stocks, ETFs, FX)

Primary source for stock/ETF prices. Covers NSE, BSE, US, and 50+ exchanges.
Free tier: 800 API calls/day, 8 calls/minute.
Docs: https://twelvedata.com/docs

Indian tickers: use symbol directly (e.g. RELIANCE, INFY) with exchange=NSE or BSE.
US tickers: use symbol directly (e.g. AAPL, MSFT).
"""

import httpx
from typing import Optional
from app.config import settings
from app.services.cache import get_cached_stock, set_cached_stock

TWELVE_BASE = "https://api.twelvedata.com"


def _get_api_key() -> Optional[str]:
    return getattr(settings, 'TWELVE_DATA_API_KEY', None)


async def get_stock_price(ticker: str, exchange: str = "") -> Optional[dict]:
    """
    Get real-time price for a stock/ETF.
    ticker: RELIANCE, INFY, AAPL, etc.
    exchange: NSE, BSE, or empty for US.
    """
    api_key = _get_api_key()
    if not api_key:
        return None

    # Check cache
    cache_key = f"{ticker}:{exchange}" if exchange else ticker
    cached = get_cached_stock(f"td:{cache_key}")
    if cached:
        return cached

    try:
        symbol = f"{ticker}" if not exchange else ticker
        params = {
            "symbol": symbol,
            "apikey": api_key,
        }
        if exchange:
            params["exchange"] = exchange

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{TWELVE_BASE}/quote", params=params)
            resp.raise_for_status()
            data = resp.json()

        if "code" in data and data["code"] != 200:
            return None  # API error

        price_data = {
            "symbol": data.get("symbol", ticker),
            "name": data.get("name", ticker),
            "price": float(data.get("close", 0) or data.get("previous_close", 0)),
            "currency": data.get("currency", "INR" if exchange in ("NSE", "BSE") else "USD"),
            "exchange": data.get("exchange", exchange),
            "source": "twelvedata",
        }
        set_cached_stock(f"td:{cache_key}", price_data)
        return price_data
    except Exception:
        return None


async def search_stocks(query: str) -> list[dict]:
    """Search for stocks across all exchanges."""
    api_key = _get_api_key()
    if not api_key:
        return []

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{TWELVE_BASE}/symbol_search", params={
                "symbol": query,
                "outputsize": 20,
            })
            resp.raise_for_status()
            data = resp.json()

        return [
            {
                "symbol": item.get("symbol", ""),
                "name": item.get("instrument_name", ""),
                "exchange": item.get("exchange", ""),
                "type": item.get("instrument_type", ""),
                "country": item.get("country", ""),
                "source": "twelvedata",
            }
            for item in data.get("data", [])
        ]
    except Exception:
        return []


async def get_forex_rate(from_currency: str = "USD", to_currency: str = "INR") -> Optional[float]:
    """Get FX rate from Twelve Data."""
    api_key = _get_api_key()
    if not api_key:
        return None

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{TWELVE_BASE}/exchange_rate", params={
                "symbol": f"{from_currency}/{to_currency}",
                "apikey": api_key,
            })
            resp.raise_for_status()
            data = resp.json()

        return float(data.get("rate", 0))
    except Exception:
        return None
