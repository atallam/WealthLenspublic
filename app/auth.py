"""
WealthLens OSS — Authentication & Session Management

TWO AUTH FLOWS:

  EMAIL/PASSWORD:
    Register → password hashes (bcrypt) + derives vault key → DEK created → JWT issued
    Login → verify bcrypt → derive vault key → decrypt DEK → JWT issued

  GOOGLE OAUTH:
    Google Sign-In (frontend) → ID token sent to backend → verified with Google
    Step 1: Google identity verified → user created (no vault yet) → "pending" JWT issued
    Step 2: User sets a "vault PIN" (4-8 char passphrase) → vault key derived → DEK created
    Step 3: On subsequent Google logins → Google verifies identity → user enters vault PIN → DEK unlocked

    The vault PIN is SHORT because Google already handles strong identity.
    It exists solely to derive the encryption key — zero-knowledge is preserved.
    The operator still cannot read any data without the user's PIN.

JWT carries:
  - user identity (sub, email)
  - wrapped DEK (AES-encrypted with server SECRET_KEY) — only present after vault is unlocked
  - vault_ready flag — tells frontend whether to show the PIN prompt
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
import bcrypt as _bcrypt
from sqlalchemy.orm import Session
import base64
import os

from app.config import settings
from app.database import get_db
from app.models import User
from app.encryption import (
    derive_vault_key, decrypt_dek, generate_user_salt,
    generate_dek, encrypt_dek, encrypt_field, decrypt_field
)

security = HTTPBearer()


def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())


# ---------------------------------------------------------------------------
# DEK protection inside JWT
# ---------------------------------------------------------------------------

def _jwt_encrypt_dek(dek: bytes) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes as crypto_hashes
    kdf = PBKDF2HMAC(
        algorithm=crypto_hashes.SHA256(), length=32,
        salt=b"wealthlens-jwt-dek-wrap", iterations=100_000,
    )
    wrap_key = kdf.derive(settings.SECRET_KEY.encode())
    aesgcm = AESGCM(wrap_key)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, dek, None)
    return base64.b64encode(nonce + ct).decode()


def _jwt_decrypt_dek(wrapped: str) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes as crypto_hashes
    kdf = PBKDF2HMAC(
        algorithm=crypto_hashes.SHA256(), length=32,
        salt=b"wealthlens-jwt-dek-wrap", iterations=100_000,
    )
    wrap_key = kdf.derive(settings.SECRET_KEY.encode())
    payload = base64.b64decode(wrapped)
    nonce, ct = payload[:12], payload[12:]
    aesgcm = AESGCM(wrap_key)
    return aesgcm.decrypt(nonce, ct, None)


# ---------------------------------------------------------------------------
# JWT creation
# ---------------------------------------------------------------------------

def create_access_token(user_id: str, email: str, dek: Optional[bytes] = None, vault_ready: bool = True) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "email": email,
        "vault_ready": vault_ready,
        "exp": expire,
    }
    if dek:
        payload["dek"] = _jwt_encrypt_dek(dek)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


class AuthContext:
    def __init__(self, user_id: str, email: str, dek: bytes):
        self.user_id = user_id
        self.email = email
        self.dek = dek


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> AuthContext:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
        email = payload.get("email")
        wrapped_dek = payload.get("dek")
        vault_ready = payload.get("vault_ready", False)

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        if not vault_ready or not wrapped_dek:
            raise HTTPException(status_code=403, detail="Vault not unlocked. Enter your vault PIN.")

        dek = _jwt_decrypt_dek(wrapped_dek)
        return AuthContext(user_id=user_id, email=email, dek=dek)
    except HTTPException:
        raise
    except JWTError:
        raise HTTPException(status_code=401, detail="Token expired or invalid")
    except Exception:
        raise HTTPException(status_code=401, detail="Authentication failed")


# ---------------------------------------------------------------------------
# Google ID Token verification
# ---------------------------------------------------------------------------

async def verify_google_token(id_token: str) -> dict:
    import httpx
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=501, detail="Google OAuth not configured. Set GOOGLE_CLIENT_ID.")

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": id_token}
        )

    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid Google token")

    payload = resp.json()
    if payload.get("aud") != settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=401, detail="Token audience mismatch")
    if payload.get("email_verified") != "true":
        raise HTTPException(status_code=401, detail="Email not verified by Google")

    return {
        "sub": payload["sub"],
        "email": payload["email"],
        "name": payload.get("name", payload["email"].split("@")[0]),
        "picture": payload.get("picture", ""),
    }


# ---------------------------------------------------------------------------
# Email/Password auth
# ---------------------------------------------------------------------------

def register_user(db: Session, email: str, password: str, display_name: str) -> tuple[User, bytes]:
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="Email already registered")

    salt = generate_user_salt()
    vault_key = derive_vault_key(password, salt)
    dek = generate_dek()
    enc_dek = encrypt_dek(dek, vault_key)

    user = User(
        email=email, display_name=display_name,
        hashed_password=hash_password(password),
        auth_provider="email",
        key_salt=salt, encrypted_dek=enc_dek,
        encrypted_portfolio="",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user, dek


def login_user(db: Session, email: str, password: str) -> tuple[User, bytes]:
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.hashed_password or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account deactivated")

    vault_key = derive_vault_key(password, user.key_salt)
    try:
        dek = decrypt_dek(user.encrypted_dek, vault_key)
    except Exception:
        raise HTTPException(status_code=401, detail="Decryption failed")
    return user, dek


# ---------------------------------------------------------------------------
# Google OAuth helpers
# ---------------------------------------------------------------------------

def google_find_or_create(db: Session, google_info: dict) -> User:
    user = db.query(User).filter(User.google_sub == google_info["sub"]).first()
    if user:
        return user

    user = db.query(User).filter(User.email == google_info["email"]).first()
    if user:
        user.google_sub = google_info["sub"]
        if not user.auth_provider or user.auth_provider == "email":
            user.auth_provider = "both"
        db.commit()
        return user

    user = User(
        email=google_info["email"],
        display_name=google_info["name"],
        auth_provider="google",
        google_sub=google_info["sub"],
        encrypted_portfolio="",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def setup_vault_pin(db: Session, user: User, pin: str) -> bytes:
    salt = generate_user_salt()
    vault_key = derive_vault_key(pin, salt)
    dek = generate_dek()
    enc_dek = encrypt_dek(dek, vault_key)

    user.key_salt = salt
    user.encrypted_dek = enc_dek
    user.hashed_password = hash_password(pin)
    db.commit()
    return dek


def unlock_vault_with_pin(db: Session, user: User, pin: str) -> bytes:
    if not user.hashed_password or not user.key_salt or not user.encrypted_dek:
        raise HTTPException(status_code=400, detail="Vault not set up. Create a vault PIN first.")
    if not verify_password(pin, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect vault PIN")

    vault_key = derive_vault_key(pin, user.key_salt)
    try:
        return decrypt_dek(user.encrypted_dek, vault_key)
    except Exception:
        raise HTTPException(status_code=401, detail="Vault decryption failed")
