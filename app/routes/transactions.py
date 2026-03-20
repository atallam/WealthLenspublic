"""
WealthLens OSS — Transaction Routes
POST   /api/transactions         — add transaction
GET    /api/transactions/{hid}   — list transactions for a holding
DELETE /api/transactions/{tid}   — delete transaction
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user, AuthContext
from app.models import Holding, Transaction
from app.schemas import TransactionCreate
from app.encryption import encrypt_json, decrypt_json

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


@router.post("", status_code=201)
def add_transaction(
    req: TransactionCreate,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Verify holding belongs to user
    holding = (
        db.query(Holding)
        .filter(Holding.id == req.holding_id, Holding.user_id == auth.user_id)
        .first()
    )
    if not holding:
        raise HTTPException(status_code=404, detail="Holding not found")

    sensitive = {
        "txn_type": req.txn_type,
        "units": req.units,
        "price": req.price,
        "price_usd": req.price_usd,
        "txn_date": req.txn_date,
        "notes": req.notes or "",
    }

    txn = Transaction(
        holding_id=req.holding_id,
        user_id=auth.user_id,
        encrypted_data=encrypt_json(sensitive, auth.dek),
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)

    return {"id": txn.id, **sensitive, "holding_id": req.holding_id}


@router.get("/{holding_id}")
def list_transactions(
    holding_id: str,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Verify ownership
    holding = (
        db.query(Holding)
        .filter(Holding.id == holding_id, Holding.user_id == auth.user_id)
        .first()
    )
    if not holding:
        raise HTTPException(status_code=404, detail="Holding not found")

    txns = (
        db.query(Transaction)
        .filter(Transaction.holding_id == holding_id)
        .order_by(Transaction.created_at.asc())
        .all()
    )

    result = []
    for t in txns:
        try:
            data = decrypt_json(t.encrypted_data, auth.dek)
            data["id"] = t.id
            data["holding_id"] = t.holding_id
            result.append(data)
        except Exception:
            continue
    return result


@router.delete("/{txn_id}")
def delete_transaction(
    txn_id: str,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    txn = (
        db.query(Transaction)
        .filter(Transaction.id == txn_id, Transaction.user_id == auth.user_id)
        .first()
    )
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    db.delete(txn)
    db.commit()
    return {"message": "Transaction deleted"}
