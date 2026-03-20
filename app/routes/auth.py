"""
WealthLens OSS — Auth Routes
POST /api/auth/register           — email/password registration
POST /api/auth/login              — email/password login
POST /api/auth/google             — Google ID token → identity verified
POST /api/auth/vault/setup        — set vault PIN (first time, after Google login)
POST /api/auth/vault/unlock       — unlock vault with PIN (returning Google users)
POST /api/auth/change-password    — change password/PIN
GET  /api/auth/me                 — current user info
GET  /api/auth/google-client-id   — return Google client ID (for frontend)
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app.auth import (
    register_user, login_user, create_access_token,
    get_current_user, AuthContext, hash_password, verify_password,
    verify_google_token, google_find_or_create,
    setup_vault_pin, unlock_vault_with_pin,
)
from app.schemas import RegisterRequest, LoginRequest, TokenResponse, PasswordChangeRequest
from app.models import User
from app.encryption import derive_vault_key, rewrap_dek
from app.config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


# --- Schemas specific to Google flow ---

class GoogleLoginRequest(BaseModel):
    id_token: str

class VaultPinRequest(BaseModel):
    pin: str  # 4-8 character vault passphrase

class GoogleAuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    display_name: str
    vault_ready: bool  # False = needs PIN setup or PIN entry
    vault_exists: bool  # True = vault exists, just needs unlocking


# --- Email/Password ---

@router.post("/register", response_model=TokenResponse)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    user, dek = register_user(db, req.email, req.password, req.display_name)
    token = create_access_token(user.id, user.email, dek)
    return TokenResponse(
        access_token=token, user_id=user.id,
        email=user.email, display_name=user.display_name,
    )


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user, dek = login_user(db, req.email, req.password)
    token = create_access_token(user.id, user.email, dek)
    return TokenResponse(
        access_token=token, user_id=user.id,
        email=user.email, display_name=user.display_name,
    )


# --- Google OAuth ---

@router.get("/google-client-id")
def get_google_client_id():
    """Return Google Client ID so frontend can initialise the Sign-In button."""
    return {
        "client_id": settings.GOOGLE_CLIENT_ID or "",
        "enabled": bool(settings.GOOGLE_CLIENT_ID),
    }


@router.post("/google", response_model=GoogleAuthResponse)
async def google_login(req: GoogleLoginRequest, db: Session = Depends(get_db)):
    """
    Verify Google ID token, find/create user.
    Returns a JWT — but vault may not be unlocked yet.
    """
    google_info = await verify_google_token(req.id_token)
    user = google_find_or_create(db, google_info)

    vault_exists = bool(user.encrypted_dek and user.key_salt)

    # If user already has email/password vault, they still need to enter their password
    # to unlock. But for pure Google users, they need their vault PIN.
    token = create_access_token(
        user.id, user.email,
        dek=None,  # Not unlocked yet
        vault_ready=False,
    )

    return GoogleAuthResponse(
        access_token=token,
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        vault_ready=False,
        vault_exists=vault_exists,
    )


@router.post("/vault/setup", response_model=TokenResponse)
def vault_setup(req: VaultPinRequest, db: Session = Depends(get_db),
                credentials=Depends(HTTPBearer())):
    """
    First-time vault setup for Google users.
    Requires a pending JWT (vault_ready=False) + a new PIN.
    """
    from jose import jwt as jose_jwt
    payload = jose_jwt.decode(credentials.credentials, settings.SECRET_KEY,
                              algorithms=[settings.ALGORITHM])
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.encrypted_dek and user.key_salt:
        raise HTTPException(status_code=409, detail="Vault already exists. Use /vault/unlock instead.")

    if len(req.pin) < 4:
        raise HTTPException(status_code=400, detail="Vault PIN must be at least 4 characters")

    dek = setup_vault_pin(db, user, req.pin)
    token = create_access_token(user.id, user.email, dek, vault_ready=True)

    return TokenResponse(
        access_token=token, user_id=user.id,
        email=user.email, display_name=user.display_name,
    )


@router.post("/vault/unlock", response_model=TokenResponse)
def vault_unlock(req: VaultPinRequest, db: Session = Depends(get_db),
                 credentials=Depends(HTTPBearer())):
    """
    Unlock existing vault with PIN (for returning Google users).
    Also works for email/password users who linked Google.
    """
    from jose import jwt as jose_jwt
    payload = jose_jwt.decode(credentials.credentials, settings.SECRET_KEY,
                              algorithms=[settings.ALGORITHM])
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    dek = unlock_vault_with_pin(db, user, req.pin)
    token = create_access_token(user.id, user.email, dek, vault_ready=True)

    return TokenResponse(
        access_token=token, user_id=user.id,
        email=user.email, display_name=user.display_name,
    )


# --- Common ---

@router.get("/me")
def get_me(auth: AuthContext = Depends(get_current_user), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == auth.user_id).first()
    return {
        "id": user.id, "email": user.email,
        "display_name": user.display_name,
        "auth_provider": user.auth_provider,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


@router.post("/change-password")
def change_password(req: PasswordChangeRequest, auth: AuthContext = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == auth.user_id).first()
    if not verify_password(req.old_password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Current password/PIN incorrect")

    old_vault_key = derive_vault_key(req.old_password, user.key_salt)
    new_vault_key = derive_vault_key(req.new_password, user.key_salt)
    user.encrypted_dek = rewrap_dek(user.encrypted_dek, old_vault_key, new_vault_key)
    user.hashed_password = hash_password(req.new_password)
    db.commit()
    return {"message": "Password/PIN changed. Please log in again."}
