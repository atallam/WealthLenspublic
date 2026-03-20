"""
WealthLens OSS — Zero-Knowledge Encryption Layer

Architecture:
  1. User registers → password → PBKDF2 derives a "vault key"
  2. A random Data Encryption Key (DEK) is generated
  3. DEK is encrypted with the vault key → stored in DB as `encrypted_dek`
  4. On login, password → vault key → decrypt DEK → held in memory (session)
  5. All sensitive fields are encrypted/decrypted with the DEK using AES-256-GCM
  6. Admin/DB operator sees only ciphertext — cannot derive vault key without password

This ensures the platform operator CANNOT read any family's financial data.
"""

import os
import base64
import json
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from app.config import settings


# ---------------------------------------------------------------------------
# Key Derivation
# ---------------------------------------------------------------------------

def derive_vault_key(password: str, user_salt: bytes) -> bytes:
    """
    Derive a 256-bit vault key from the user's password + unique salt.
    The master salt from config is mixed in so even identical passwords
    across instances produce different keys.
    """
    combined_salt = user_salt + settings.ENCRYPTION_MASTER_SALT.encode()
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=combined_salt,
        iterations=600_000,  # OWASP recommended minimum
    )
    return kdf.derive(password.encode())


def generate_user_salt() -> bytes:
    """Generate a random 16-byte salt for a new user."""
    return os.urandom(16)


# ---------------------------------------------------------------------------
# Data Encryption Key (DEK) Management
# ---------------------------------------------------------------------------

def generate_dek() -> bytes:
    """Generate a random 256-bit Data Encryption Key."""
    return AESGCM.generate_key(bit_length=256)


def encrypt_dek(dek: bytes, vault_key: bytes) -> str:
    """Encrypt the DEK with the vault key. Returns base64 string for DB storage."""
    aesgcm = AESGCM(vault_key)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, dek, None)
    # Store as base64: nonce || ciphertext
    payload = nonce + ct
    return base64.b64encode(payload).decode()


def decrypt_dek(encrypted_dek_b64: str, vault_key: bytes) -> bytes:
    """Decrypt the DEK using the vault key. Returns raw DEK bytes."""
    payload = base64.b64decode(encrypted_dek_b64)
    nonce = payload[:12]
    ct = payload[12:]
    aesgcm = AESGCM(vault_key)
    return aesgcm.decrypt(nonce, ct, None)


# ---------------------------------------------------------------------------
# Field-Level Encryption (used for sensitive data columns)
# ---------------------------------------------------------------------------

def encrypt_field(plaintext: str, dek: bytes) -> str:
    """
    Encrypt a string field with the user's DEK.
    Returns base64(nonce || ciphertext || tag).
    """
    if not plaintext:
        return ""
    aesgcm = AESGCM(dek)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ct).decode()


def decrypt_field(ciphertext_b64: str, dek: bytes) -> str:
    """Decrypt a base64-encoded field back to plaintext."""
    if not ciphertext_b64:
        return ""
    payload = base64.b64decode(ciphertext_b64)
    nonce = payload[:12]
    ct = payload[12:]
    aesgcm = AESGCM(dek)
    return aesgcm.decrypt(nonce, ct, None).decode()


# ---------------------------------------------------------------------------
# JSON blob encryption (for portfolio JSONB-equivalent data)
# ---------------------------------------------------------------------------

def encrypt_json(data: dict | list, dek: bytes) -> str:
    """Serialize a dict/list to JSON, then encrypt."""
    return encrypt_field(json.dumps(data, default=str), dek)


def decrypt_json(ciphertext_b64: str, dek: bytes) -> dict | list:
    """Decrypt and parse JSON."""
    plaintext = decrypt_field(ciphertext_b64, dek)
    if not plaintext:
        return {}
    return json.loads(plaintext)


# ---------------------------------------------------------------------------
# Password change: re-wrap DEK with new vault key
# ---------------------------------------------------------------------------

def rewrap_dek(encrypted_dek_b64: str, old_vault_key: bytes, new_vault_key: bytes) -> str:
    """
    When a user changes their password, decrypt the DEK with the old key
    and re-encrypt with the new key. All data stays intact.
    """
    dek = decrypt_dek(encrypted_dek_b64, old_vault_key)
    return encrypt_dek(dek, new_vault_key)
