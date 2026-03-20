"""
WealthLens OSS — Holdings Routes (encrypted CRUD)
GET    /api/holdings          — list all holdings (decrypted + enriched)
POST   /api/holdings          — create holding
PUT    /api/holdings/{id}     — update holding
DELETE /api/holdings/{id}     — delete holding
"""

import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user, AuthContext
from app.models import Holding, Transaction, Artifact
from app.schemas import HoldingCreate, HoldingUpdate, HoldingResponse
from app.encryption import encrypt_json, decrypt_json

router = APIRouter(prefix="/api/holdings", tags=["holdings"])


def _enrich_holding(holding_data: dict, transactions_data: list) -> dict:
    """Server-side enrichment: compute net_units and avg_cost from transactions."""
    buys = [t for t in transactions_data if t.get("txn_type") == "BUY"]
    sells = [t for t in transactions_data if t.get("txn_type") == "SELL"]

    total_buy_units = sum(t.get("units", 0) for t in buys)
    total_sell_units = sum(t.get("units", 0) for t in sells)
    total_buy_cost = sum(t.get("units", 0) * t.get("price", 0) for t in buys)

    holding_data["net_units"] = total_buy_units - total_sell_units
    holding_data["avg_cost"] = (
        total_buy_cost / total_buy_units if total_buy_units > 0 else 0
    )
    return holding_data


@router.get("")
def list_holdings(
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all holdings for the authenticated user, decrypted and enriched."""
    holdings = (
        db.query(Holding)
        .filter(Holding.user_id == auth.user_id)
        .order_by(Holding.created_at.desc())
        .all()
    )

    result = []
    for h in holdings:
        try:
            data = decrypt_json(h.encrypted_data, auth.dek)
        except Exception:
            continue  # skip corrupted records

        data["id"] = h.id
        data["type"] = h.asset_type
        data["member_id"] = h.member_id

        # Decrypt transactions
        txns_raw = (
            db.query(Transaction)
            .filter(Transaction.holding_id == h.id)
            .order_by(Transaction.created_at.asc())
            .all()
        )
        txns = []
        for t in txns_raw:
            try:
                td = decrypt_json(t.encrypted_data, auth.dek)
                td["id"] = t.id
                td["holding_id"] = t.holding_id
                txns.append(td)
            except Exception:
                continue

        # Decrypt artifacts
        arts_raw = (
            db.query(Artifact).filter(Artifact.holding_id == h.id).all()
        )
        arts = []
        for a in arts_raw:
            try:
                ad = decrypt_json(a.encrypted_meta, auth.dek)
                ad["id"] = a.id
                ad["holding_id"] = a.holding_id
                arts.append(ad)
            except Exception:
                continue

        data["transactions"] = txns
        data["artifacts"] = arts
        data = _enrich_holding(data, txns)
        result.append(data)

    return result


@router.post("", status_code=201)
def create_holding(
    req: HoldingCreate,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new holding. Sensitive data is encrypted before storage."""
    sensitive = {
        "name": req.name,
        "ticker": req.ticker,
        "scheme_code": req.scheme_code,
        "purchase_value": req.purchase_value,
        "current_value": req.current_value,
        "principal": req.principal,
        "interest_rate": req.interest_rate,
        "usd_inr_rate": req.usd_inr_rate,
        "start_date": req.start_date,
        "maturity_date": req.maturity_date,
    }

    holding = Holding(
        user_id=auth.user_id,
        asset_type=req.type,
        member_id=req.member_id,
        encrypted_data=encrypt_json(sensitive, auth.dek),
    )
    db.add(holding)
    db.commit()
    db.refresh(holding)

    return {
        "id": holding.id,
        "message": "Holding created",
        **sensitive,
        "type": req.type,
        "member_id": req.member_id,
        "net_units": 0,
        "avg_cost": 0,
        "transactions": [],
        "artifacts": [],
    }


@router.put("/{holding_id}")
def update_holding(
    holding_id: str,
    req: HoldingUpdate,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a holding's encrypted data."""
    holding = (
        db.query(Holding)
        .filter(Holding.id == holding_id, Holding.user_id == auth.user_id)
        .first()
    )
    if not holding:
        raise HTTPException(status_code=404, detail="Holding not found")

    # Decrypt existing, merge updates, re-encrypt
    data = decrypt_json(holding.encrypted_data, auth.dek)
    updates = req.model_dump(exclude_none=True)
    data.update(updates)
    holding.encrypted_data = encrypt_json(data, auth.dek)

    db.commit()
    return {"id": holding_id, "message": "Updated", **data}


@router.delete("/{holding_id}")
def delete_holding(
    holding_id: str,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a holding and all its transactions/artifacts (cascade)."""
    holding = (
        db.query(Holding)
        .filter(Holding.id == holding_id, Holding.user_id == auth.user_id)
        .first()
    )
    if not holding:
        raise HTTPException(status_code=404, detail="Holding not found")

    db.delete(holding)
    db.commit()
    return {"message": "Deleted"}
