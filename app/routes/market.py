"""
WealthLens OSS — Market Data Routes (multi-source)

MF:     MFAPI → AMFI daily → AMFI historical → mftool → manual
Stocks: Twelve Data → Yahoo Finance → manual
FX:     exchangerate-api → Twelve Data → Yahoo → hardcoded
"""

import asyncio
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user, AuthContext
from app.models import Holding, Transaction
from app.schemas import SIPNavRequest
from app.encryption import decrypt_json, encrypt_json
from app.services import mfapi
from app.services import stocks as stock_svc
from app.services import fx as fx_svc

router = APIRouter(prefix="/api", tags=["market"])


class ManualNAVRequest(BaseModel):
    holding_id: str
    nav: float
    nav_date: Optional[str] = ""
    notes: Optional[str] = "Manual NAV entry"


# ── Mutual Funds (4-source) ──

@router.get("/mf/search")
async def mf_search(q: str):
    results = await mfapi.search_mf(q)
    return results[:20]


@router.get("/mf/amfi/search")
async def amfi_only_search(q: str):
    results = await mfapi.amfi_search(q)
    return [r for r in results[:20]]


@router.get("/mf/nav/{scheme_code}")
async def mf_nav(scheme_code: str):
    result = await mfapi.get_latest_nav(scheme_code)
    if not result:
        raise HTTPException(status_code=404, detail="Scheme not found across all sources. Use manual NAV.")
    return result


@router.post("/mf/sip-navs")
async def mf_sip_navs(req: SIPNavRequest):
    return await mfapi.get_sip_navs(req.scheme_code, req.dates)


@router.post("/mf/manual-nav")
async def manual_nav_update(req: ManualNAVRequest, auth: AuthContext = Depends(get_current_user),
                            db: Session = Depends(get_db)):
    holding = db.query(Holding).filter(Holding.id == req.holding_id, Holding.user_id == auth.user_id).first()
    if not holding:
        raise HTTPException(status_code=404, detail="Holding not found")

    data = decrypt_json(holding.encrypted_data, auth.dek)
    net_units = _compute_net_units(db, holding.id, auth.dek)

    data["current_value"] = net_units * req.nav if net_units > 0 else req.nav
    data["manual_nav"] = req.nav
    data["manual_nav_date"] = req.nav_date

    holding.encrypted_data = encrypt_json(data, auth.dek)
    db.commit()
    return {"message": "NAV updated", "holding_id": req.holding_id, "nav": req.nav,
            "net_units": net_units, "current_value": data["current_value"], "source": "manual"}


# ── Stocks & ETFs (Twelve Data → Yahoo) ──

@router.get("/stock/info/{ticker}")
async def stock_info(ticker: str, exchange: str = ""):
    result = await stock_svc.get_price(ticker, exchange)
    if not result:
        raise HTTPException(status_code=404, detail="Ticker not found")
    return result


@router.get("/etf/search")
async def etf_search(q: str):
    return await stock_svc.search(q)


# ── FX (exchangerate-api → Twelve Data → Yahoo) ──

@router.get("/forex/usdinr")
async def forex_usdinr():
    rate = await fx_svc.get_usd_inr()
    return {"rate": rate}


# ── Data Source Status (for frontend diagnostics) ──

@router.get("/sources/status")
async def sources_status():
    """Check which data sources are currently reachable."""
    from app.config import settings
    return {
        "mf_sources": ["mfapi", "amfi_daily", "amfi_historical", "mftool"],
        "stock_sources": [
            {"name": "twelvedata", "configured": bool(settings.TWELVE_DATA_API_KEY)},
            {"name": "yahoo", "configured": True},
        ],
        "fx_sources": ["exchangerate-api", "twelvedata", "yahoo", "hardcoded"],
    }


# ── Batch Price Refresh (parallel, multi-source) ──

@router.post("/prices/refresh")
async def refresh_prices(auth: AuthContext = Depends(get_current_user), db: Session = Depends(get_db)):
    holdings = db.query(Holding).filter(Holding.user_id == auth.user_id).all()
    usd_inr = await fx_svc.get_usd_inr()

    # Build parallel fetch jobs
    jobs = []
    for h in holdings:
        try:
            data = decrypt_json(h.encrypted_data, auth.dek)
        except Exception:
            continue

        net_units = _compute_net_units(db, h.id, auth.dek)
        at = h.asset_type
        ticker = data.get("ticker", "")
        scheme_code = data.get("scheme_code", "")

        if at == "MF" and scheme_code:
            jobs.append((h, data, net_units, mfapi.get_latest_nav(scheme_code), "mf"))
        elif at in ("IN_STOCK", "IN_ETF") and ticker:
            jobs.append((h, data, net_units, stock_svc.get_price(ticker, "NSE"), "in"))
        elif at == "US_STOCK" and ticker:
            jobs.append((h, data, net_units, stock_svc.get_price(ticker), "us"))

    if not jobs:
        return {"updated_count": 0, "errors": [], "usd_inr": usd_inr}

    # Fire all in parallel
    results = await asyncio.gather(*[j[3] for j in jobs], return_exceptions=True)

    updated, errors = 0, []
    for (h, data, nu, _, kind), result in zip(jobs, results):
        if isinstance(result, Exception) or not result:
            errors.append(f"{h.id}: no data")
            continue
        try:
            if kind == "mf":
                data["current_value"] = nu * result["nav"]
                data["nav_source"] = result.get("source", "")
            elif kind == "in":
                data["current_value"] = nu * result["price"]
            elif kind == "us":
                data["current_value"] = nu * result["price"] * usd_inr
                data["usd_inr_rate"] = usd_inr

            h.encrypted_data = encrypt_json(data, auth.dek)
            updated += 1
        except Exception as e:
            errors.append(f"{h.id}: {str(e)}")

    db.commit()
    return {"updated_count": updated, "errors": errors, "usd_inr": usd_inr}


# ── Helper ──

def _compute_net_units(db: Session, holding_id: str, dek: bytes) -> float:
    txns = db.query(Transaction).filter(Transaction.holding_id == holding_id).all()
    net = 0.0
    for t in txns:
        try:
            td = decrypt_json(t.encrypted_data, dek)
            if td.get("txn_type") == "BUY": net += td.get("units", 0)
            elif td.get("txn_type") == "SELL": net -= td.get("units", 0)
        except Exception:
            pass
    return net
