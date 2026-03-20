"""
WealthLens OSS — SQLAlchemy Models

Multi-tenant design: every table is scoped by user_id.
Sensitive fields are stored encrypted (AES-256-GCM) — the DB only sees ciphertext.
"""

from datetime import datetime
from sqlalchemy import (
    Column, String, Text, Float, Boolean, DateTime,
    ForeignKey, Index, LargeBinary
)
from sqlalchemy.orm import relationship
from app.database import Base
import nanoid


def gen_id() -> str:
    return nanoid.generate(size=21)


class User(Base):
    __tablename__ = "users"

    id = Column(String(21), primary_key=True, default=gen_id)
    email = Column(String(255), unique=True, nullable=False, index=True)
    display_name = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=True)  # Vault passphrase hash (nullable for pending Google users)

    # Auth provider
    auth_provider = Column(String(20), default="email")  # "email" or "google"
    google_sub = Column(String(255), nullable=True)       # Google user ID

    # Encryption infrastructure
    key_salt = Column(LargeBinary(16), nullable=True)       # PBKDF2 salt (set when vault passphrase is created)
    encrypted_dek = Column(Text, nullable=True)              # AES-wrapped DEK

    # Portfolio metadata (encrypted JSON blob)
    encrypted_portfolio = Column(Text, default="")  # members, goals, alerts

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    holdings = relationship("Holding", back_populates="user", cascade="all, delete-orphan")


class Holding(Base):
    __tablename__ = "holdings"

    id = Column(String(21), primary_key=True, default=gen_id)
    user_id = Column(String(21), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Encrypted sensitive fields (instrument name, values, etc.)
    encrypted_data = Column(Text, nullable=False)
    # Stores JSON: {name, type, ticker, scheme_code, member_id,
    #               purchase_value, current_value, principal,
    #               interest_rate, usd_inr_rate, start_date, maturity_date}

    # Non-sensitive metadata for server-side queries
    asset_type = Column(String(50), nullable=False)  # for filtering without decryption
    member_id = Column(String(21), nullable=False)    # for member filtering

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="holdings")
    transactions = relationship("Transaction", back_populates="holding", cascade="all, delete-orphan")
    artifacts = relationship("Artifact", back_populates="holding", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_holdings_user_type", "user_id", "asset_type"),
        Index("ix_holdings_user_member", "user_id", "member_id"),
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(String(21), primary_key=True, default=gen_id)
    holding_id = Column(String(21), ForeignKey("holdings.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(21), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Encrypted transaction details
    encrypted_data = Column(Text, nullable=False)
    # Stores JSON: {txn_type, units, price, price_usd, txn_date, notes}

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    holding = relationship("Holding", back_populates="transactions")

    __table_args__ = (
        Index("ix_transactions_holding", "holding_id"),
        Index("ix_transactions_user", "user_id"),
    )


class Artifact(Base):
    __tablename__ = "artifacts"

    id = Column(String(21), primary_key=True, default=gen_id)
    holding_id = Column(String(21), ForeignKey("holdings.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(21), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Encrypted metadata
    encrypted_meta = Column(Text, nullable=False)
    # Stores JSON: {filename, description}

    # Encrypted file content (stored as base64-encrypted blob)
    encrypted_file = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    holding = relationship("Holding", back_populates="artifacts")

    __table_args__ = (
        Index("ix_artifacts_holding", "holding_id"),
    )
