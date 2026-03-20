"""
WealthLens OSS — Portfolio Routes (members, goals, alerts)
GET  /api/portfolio     — get decrypted portfolio (members, goals, alerts)
PUT  /api/portfolio     — save portfolio
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user, AuthContext
from app.models import User
from app.schemas import PortfolioData
from app.encryption import encrypt_json, decrypt_json

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("")
def get_portfolio(
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == auth.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.encrypted_portfolio:
        return {"members": [], "goals": [], "alerts": []}

    try:
        data = decrypt_json(user.encrypted_portfolio, auth.dek)
    except Exception:
        return {"members": [], "goals": [], "alerts": []}

    return data


@router.put("")
def save_portfolio(
    req: PortfolioData,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == auth.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    payload = req.model_dump()
    user.encrypted_portfolio = encrypt_json(payload, auth.dek)
    db.commit()
    return {"message": "Portfolio saved", **payload}
