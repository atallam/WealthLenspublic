"""
WealthLens OSS — Mutual Fund NAV Service (4-source fallback)

Chain:
  1. MFAPI.in       — fast REST API, ~95% coverage, full history
  2. AMFI NAVAll.txt — official daily file, 100% SEBI coverage
  3. AMFI Historical — official date-range download, 100% coverage
  4. mftool library  — Python library wrapping AMFI (in-process, no network on cache hit)

All free, no API keys needed.
"""

import httpx
from datetime import datetime, timedelta
from typing import Optional
from app.services.cache import (
    cache_json_get, cache_json_set, get_cached_nav, set_cached_nav,
    get_cached_mf_search, set_cached_mf_search, TTL_NAV, TTL_AMFI, TTL_SEARCH
)

MFAPI_BASE = "https://api.mfapi.in/mf"
AMFI_NAV_URL = "https://www.amfiindia.com/spages/NAVAll.txt"
AMFI_HIST_URL = "http://portal.amfiindia.com/DownloadNAVHistoryReport_Po.aspx"

# ═══════════════════════════════════════════════════════
# Source 1: MFAPI.in
# ═══════════════════════════════════════════════════════

async def _mfapi_search(query: str) -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(f"{MFAPI_BASE}/search", params={"q": query})
            resp.raise_for_status()
            return [{"schemeCode": str(r.get("schemeCode", "")),
                     "schemeName": r.get("schemeName", ""),
                     "source": "mfapi"} for r in resp.json()]
    except Exception:
        return []


async def _mfapi_nav(scheme_code: str) -> Optional[dict]:
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(f"{MFAPI_BASE}/{scheme_code}")
            resp.raise_for_status()
            data = resp.json()
        entries = data.get("data", [])
        if entries:
            return {"nav": float(entries[0]["nav"]), "date": entries[0]["date"], "source": "mfapi"}
    except Exception:
        pass
    return None


async def _mfapi_history(scheme_code: str) -> list[dict]:
    """Full NAV history from MFAPI — returns [{date, nav}, ...] newest first."""
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            resp = await client.get(f"{MFAPI_BASE}/{scheme_code}")
            resp.raise_for_status()
            return resp.json().get("data", [])
    except Exception:
        return []


# ═══════════════════════════════════════════════════════
# Source 2: AMFI NAVAll.txt (daily, 100% schemes)
# ═══════════════════════════════════════════════════════

async def _amfi_daily_file() -> dict:
    """Parse AMFI daily NAV file. Cached 1 hour. Returns {code: {name, nav, date}}."""
    cached = cache_json_get("amfi:daily")
    if cached:
        return cached

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(AMFI_NAV_URL)
            resp.raise_for_status()
            text = resp.text
    except Exception:
        return {}

    result = {}
    for line in text.split("\n"):
        parts = line.strip().split(";")
        if len(parts) >= 6:
            code, name = parts[0].strip(), parts[4].strip() if len(parts) > 4 else ""
            try:
                nav = float(parts[5].strip())
                date = parts[6].strip() if len(parts) > 6 else ""
                result[code] = {"name": name, "nav": nav, "date": date}
            except (ValueError, IndexError):
                continue

    if result:
        cache_json_set("amfi:daily", result, TTL_AMFI)
    return result


async def _amfi_nav(scheme_code: str) -> Optional[dict]:
    data = await _amfi_daily_file()
    info = data.get(scheme_code)
    if info:
        return {"nav": info["nav"], "date": info["date"], "source": "amfi_daily"}
    return None


async def _amfi_search(query: str) -> list[dict]:
    data = await _amfi_daily_file()
    q = query.lower()
    return [{"schemeCode": code, "schemeName": info["name"], "source": "amfi"}
            for code, info in data.items() if q in info["name"].lower()][:30]


# ═══════════════════════════════════════════════════════
# Source 3: AMFI Historical (date-range download)
# ═══════════════════════════════════════════════════════

async def _amfi_historical_nav(scheme_code: str, target_date: str) -> Optional[dict]:
    """
    Fetch NAV for a specific date from AMFI historical endpoint.
    target_date: DD-Mon-YYYY (e.g. 15-Jan-2024) or DD-MM-YYYY.
    """
    try:
        dt = datetime.strptime(target_date, "%d-%m-%Y")
    except ValueError:
        try:
            dt = datetime.strptime(target_date, "%Y-%m-%d")
        except ValueError:
            return None

    from_dt = (dt - timedelta(days=7)).strftime("%d-%b-%Y")
    to_dt = (dt + timedelta(days=7)).strftime("%d-%b-%Y")

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(AMFI_HIST_URL, params={
                "tp": "1", "frmdt": from_dt, "todt": to_dt
            })
            resp.raise_for_status()
            text = resp.text
    except Exception:
        return None

    # Parse: Scheme Code;ISIN;...;Scheme Name;Net Asset Value;Date
    target_str = dt.strftime("%d-%b-%Y")
    best, best_diff = None, 999

    for line in text.split("\n"):
        parts = line.strip().split(";")
        if len(parts) >= 5 and parts[0].strip() == scheme_code:
            try:
                nav = float(parts[-2].strip())
                nav_date = parts[-1].strip()
                nav_dt = datetime.strptime(nav_date, "%d-%b-%Y")
                diff = abs((nav_dt - dt).days)
                if diff < best_diff:
                    best_diff = diff
                    best = {"nav": nav, "nav_date": nav_date,
                            "is_estimated": diff > 0, "source": "amfi_historical"}
            except (ValueError, IndexError):
                continue

    return best


# ═══════════════════════════════════════════════════════
# Source 4: mftool Python library (wraps AMFI, cached)
# ═══════════════════════════════════════════════════════

def _mftool_nav(scheme_code: str) -> Optional[dict]:
    """Synchronous fallback using mftool library."""
    try:
        from mftool import Mftool
        mf = Mftool()
        data = mf.get_scheme_quote(scheme_code)
        if data and data.get("nav"):
            return {
                "nav": float(data["nav"]),
                "date": data.get("last_updated", ""),
                "source": "mftool",
            }
    except Exception:
        pass
    return None


def _mftool_search(query: str) -> list[dict]:
    """Search using mftool (synchronous)."""
    try:
        from mftool import Mftool
        mf = Mftool()
        codes = mf.get_scheme_codes()  # {code: name}
        q = query.lower()
        return [{"schemeCode": code, "schemeName": name, "source": "mftool"}
                for code, name in codes.items() if q in name.lower()][:30]
    except Exception:
        return []


# ═══════════════════════════════════════════════════════
# PUBLIC API: Cascading fallback
# ═══════════════════════════════════════════════════════

async def search_mf(query: str) -> list[dict]:
    """Search MF schemes — MFAPI → AMFI → mftool."""
    # Check cache
    cached = get_cached_mf_search(query)
    if cached:
        return cached

    # Source 1: MFAPI
    results = await _mfapi_search(query)
    if results:
        set_cached_mf_search(query, results)
        return results

    # Source 2: AMFI daily file
    results = await _amfi_search(query)
    if results:
        set_cached_mf_search(query, results)
        return results

    # Source 3: mftool (synchronous, in-process)
    results = _mftool_search(query)
    if results:
        set_cached_mf_search(query, results)
    return results


async def get_latest_nav(scheme_code: str) -> Optional[dict]:
    """Get latest NAV — MFAPI → AMFI daily → mftool."""
    # Check cache
    cached = get_cached_nav(scheme_code)
    if cached:
        return cached

    # Source 1: MFAPI
    result = await _mfapi_nav(scheme_code)
    if result:
        set_cached_nav(scheme_code, result)
        return result

    # Source 2: AMFI daily file
    result = await _amfi_nav(scheme_code)
    if result:
        set_cached_nav(scheme_code, result)
        return result

    # Source 3: mftool
    result = _mftool_nav(scheme_code)
    if result:
        set_cached_nav(scheme_code, result)
        return result

    return None


async def get_nav_for_date(scheme_code: str, target_date: str) -> dict:
    """Get NAV for specific date — MFAPI history → AMFI historical → latest NAV."""
    # Source 1: MFAPI full history
    entries = await _mfapi_history(scheme_code)
    if entries:
        nav_map = {e["date"]: float(e["nav"]) for e in entries}

        if target_date in nav_map:
            return {"nav": nav_map[target_date], "nav_date": target_date,
                    "is_estimated": False, "source": "mfapi"}

        try:
            td = datetime.strptime(target_date, "%d-%m-%Y")
        except ValueError:
            td = datetime.strptime(target_date, "%Y-%m-%d")

        best, best_diff = None, 999
        for delta in range(-7, 8):
            check = (td + timedelta(days=delta)).strftime("%d-%m-%Y")
            if check in nav_map and abs(delta) < best_diff:
                best_diff = abs(delta)
                best = {"nav": nav_map[check], "nav_date": check,
                        "is_estimated": delta != 0, "source": "mfapi"}
        if best:
            return best

    # Source 2: AMFI historical endpoint
    result = await _amfi_historical_nav(scheme_code, target_date)
    if result:
        return result

    # Source 3: Fallback to latest NAV
    latest = await get_latest_nav(scheme_code)
    if latest:
        return {"nav": latest["nav"], "nav_date": latest.get("date", ""),
                "is_estimated": True, "source": latest.get("source", "fallback")}

    return {"nav": 0, "nav_date": target_date, "is_estimated": True, "source": "none"}


async def get_sip_navs(scheme_code: str, dates: list[dict]) -> list[dict]:
    """Bulk NAV fetch for SIP — fetches MFAPI history once, then maps."""
    entries = await _mfapi_history(scheme_code)
    nav_map = {e["date"]: float(e["nav"]) for e in entries} if entries else {}
    latest_nav, latest_date = (float(entries[0]["nav"]), entries[0]["date"]) if entries else (0, "")

    # If MFAPI failed, try AMFI/mftool for latest
    if not latest_nav:
        latest = await get_latest_nav(scheme_code)
        if latest:
            latest_nav = latest["nav"]
            latest_date = latest.get("date", "")

    results = []
    for d in dates:
        try:
            target = datetime(int(d["year"]), int(d["month"]), int(d.get("day", 1)))
        except (ValueError, KeyError):
            results.append({"nav": 0, "nav_date": "", "is_estimated": True, "source": "none"})
            continue

        if target > datetime.now():
            results.append({"nav": latest_nav, "nav_date": latest_date,
                            "is_estimated": True, "source": "latest"})
            continue

        target_str = target.strftime("%d-%m-%Y")
        if target_str in nav_map:
            results.append({"nav": nav_map[target_str], "nav_date": target_str,
                            "is_estimated": False, "source": "mfapi"})
            continue

        best, best_diff = None, 999
        for delta in range(-7, 8):
            check = (target + timedelta(days=delta)).strftime("%d-%m-%Y")
            if check in nav_map and abs(delta) < best_diff:
                best_diff = abs(delta)
                best = {"nav": nav_map[check], "nav_date": check,
                        "is_estimated": True, "source": "mfapi"}

        results.append(best or {"nav": latest_nav, "nav_date": latest_date,
                                "is_estimated": True, "source": "fallback"})
    return results


async def amfi_search(query: str) -> list[dict]:
    """Direct AMFI search (exposed for the /api/mf/amfi/search endpoint)."""
    return await _amfi_search(query)
