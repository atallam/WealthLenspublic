"""
WealthLens OSS — Cache Layer (Redis or in-memory fallback)

Caches market data to avoid hammering MFAPI/Yahoo on every request:
  - MF NAVs: 5 minute TTL (NAVs update once daily, 5min is conservative)
  - Stock prices: 1 minute TTL (near real-time)
  - USD/INR rate: 2 minute TTL
  - AMFI NAV file: 1 hour TTL (published once daily)
  - MF search results: 10 minute TTL

Falls back to in-memory dict if Redis is unavailable (single-process only).
"""

import json
import time
from typing import Optional
from app.config import settings

_redis_client = None
_memory_cache: dict = {}


def _get_redis():
    """Lazy-init Redis connection."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    redis_url = getattr(settings, 'REDIS_URL', None)
    if not redis_url:
        return None

    try:
        import redis
        _redis_client = redis.from_url(redis_url, decode_responses=True)
        _redis_client.ping()
        return _redis_client
    except Exception:
        _redis_client = None
        return None


def cache_get(key: str) -> Optional[str]:
    """Get a cached value. Returns None on miss."""
    r = _get_redis()
    if r:
        try:
            return r.get(f"wl:{key}")
        except Exception:
            pass

    # In-memory fallback
    entry = _memory_cache.get(key)
    if entry and entry["exp"] > time.time():
        return entry["val"]
    return None


def cache_set(key: str, value: str, ttl_seconds: int = 300):
    """Set a cached value with TTL."""
    r = _get_redis()
    if r:
        try:
            r.setex(f"wl:{key}", ttl_seconds, value)
            return
        except Exception:
            pass

    # In-memory fallback
    _memory_cache[key] = {"val": value, "exp": time.time() + ttl_seconds}


def cache_json_get(key: str) -> Optional[dict | list]:
    """Get cached JSON."""
    raw = cache_get(key)
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    return None


def cache_json_set(key: str, data: dict | list, ttl_seconds: int = 300):
    """Cache JSON data."""
    cache_set(key, json.dumps(data, default=str), ttl_seconds)


# ---------------------------------------------------------------------------
# Convenience wrappers for market data
# ---------------------------------------------------------------------------

TTL_NAV = 300        # 5 minutes
TTL_STOCK = 60       # 1 minute
TTL_FX = 120         # 2 minutes
TTL_SEARCH = 600     # 10 minutes
TTL_AMFI = 3600      # 1 hour


def get_cached_nav(scheme_code: str) -> Optional[dict]:
    return cache_json_get(f"nav:{scheme_code}")


def set_cached_nav(scheme_code: str, data: dict):
    cache_json_set(f"nav:{scheme_code}", data, TTL_NAV)


def get_cached_stock(ticker: str) -> Optional[dict]:
    return cache_json_get(f"stock:{ticker}")


def set_cached_stock(ticker: str, data: dict):
    cache_json_set(f"stock:{ticker}", data, TTL_STOCK)


def get_cached_fx() -> Optional[float]:
    raw = cache_get("fx:usdinr")
    return float(raw) if raw else None


def set_cached_fx(rate: float):
    cache_set("fx:usdinr", str(rate), TTL_FX)


def get_cached_mf_search(query: str) -> Optional[list]:
    return cache_json_get(f"mfsearch:{query.lower().strip()}")


def set_cached_mf_search(query: str, results: list):
    cache_json_set(f"mfsearch:{query.lower().strip()}", results, TTL_SEARCH)
