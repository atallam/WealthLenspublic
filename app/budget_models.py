"""
WealthLens OSS — Budget Models (encrypted)

Tables:
  budget_imports     — record of every statement upload (source, date range, status)
  budget_transactions — individual transactions from imports (encrypted)
  budget_categories  — user-defined or AI-suggested categories
  budget_buckets     — monthly budget limits per category

All financial data (amounts, descriptions, merchant names) is encrypted.
Only metadata (category_id, month, source_type) is plaintext for queries.
"""

from datetime import datetime
from sqlalchemy import (
    Column, String, Text, Float, Integer, Boolean, DateTime, Date,
    ForeignKey, Index
)
from sqlalchemy.orm import relationship
from app.database import Base
from app.models import gen_id


class BudgetImport(Base):
    __tablename__ = "budget_imports"

    id = Column(String(21), primary_key=True, default=gen_id)
    user_id = Column(String(21), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Metadata (plaintext for queries)
    source_type = Column(String(50), nullable=False)  # hdfc_csv, sbi_csv, icici_csv, axis_csv, kotak_csv, generic_csv, pdf, manual
    source_name = Column(String(255), default="")      # "HDFC Bank", "SBI Credit Card", etc.
    file_name = Column(String(255), default="")         # Original filename
    status = Column(String(20), default="processing")   # processing, completed, failed, partial
    transaction_count = Column(Integer, default=0)
    date_range_start = Column(Date, nullable=True)
    date_range_end = Column(Date, nullable=True)

    # Encrypted summary (total debits, credits, etc.)
    encrypted_summary = Column(Text, default="")

    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)  # 1 year retention

    # Relationships
    transactions = relationship("BudgetTransaction", back_populates="budget_import", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_budget_imports_user", "user_id"),
        Index("ix_budget_imports_user_date", "user_id", "created_at"),
    )


class BudgetTransaction(Base):
    __tablename__ = "budget_transactions"

    id = Column(String(21), primary_key=True, default=gen_id)
    user_id = Column(String(21), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    import_id = Column(String(21), ForeignKey("budget_imports.id", ondelete="CASCADE"), nullable=True)

    # Plaintext metadata (for filtering/grouping without decryption)
    txn_date = Column(Date, nullable=False)
    txn_month = Column(String(7), nullable=False)  # YYYY-MM for monthly grouping
    txn_type = Column(String(10), nullable=False)   # debit | credit
    category_id = Column(String(21), nullable=True)  # FK to budget_categories
    source_type = Column(String(50), default="")     # import source

    # Encrypted transaction details
    encrypted_data = Column(Text, nullable=False)
    # Contains: {description, amount, balance, merchant, reference, raw_line}

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    budget_import = relationship("BudgetImport", back_populates="transactions")

    __table_args__ = (
        Index("ix_budget_txn_user_month", "user_id", "txn_month"),
        Index("ix_budget_txn_user_cat", "user_id", "category_id"),
        Index("ix_budget_txn_user_type", "user_id", "txn_type"),
        Index("ix_budget_txn_import", "import_id"),
    )


class BudgetCategory(Base):
    __tablename__ = "budget_categories"

    id = Column(String(21), primary_key=True, default=gen_id)
    user_id = Column(String(21), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    name = Column(String(100), nullable=False)      # "Groceries", "Dining", "EMI", etc.
    icon = Column(String(10), default="")            # emoji or short code
    color = Column(String(10), default="#6b7280")    # hex color for charts
    is_income = Column(Boolean, default=False)       # True for salary, interest, etc.
    is_system = Column(Boolean, default=False)       # True for auto-created categories
    sort_order = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_budget_cat_user", "user_id"),
    )


class BudgetBucket(Base):
    __tablename__ = "budget_buckets"

    id = Column(String(21), primary_key=True, default=gen_id)
    user_id = Column(String(21), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    category_id = Column(String(21), ForeignKey("budget_categories.id", ondelete="CASCADE"), nullable=False)
    month = Column(String(7), nullable=False)        # YYYY-MM
    budget_limit = Column(Float, nullable=False)      # Monthly budget in INR
    notes = Column(Text, default="")

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_budget_bucket_user_month", "user_id", "month"),
    )


# ─── Default categories for new users ───

DEFAULT_CATEGORIES = [
    {"name": "Groceries", "icon": "🛒", "color": "#22c55e", "is_income": False},
    {"name": "Dining & Food", "icon": "🍽", "color": "#f59e0b", "is_income": False},
    {"name": "Transport", "icon": "🚗", "color": "#3b82f6", "is_income": False},
    {"name": "Shopping", "icon": "🛍", "color": "#ec4899", "is_income": False},
    {"name": "Utilities & Bills", "icon": "💡", "color": "#8b5cf6", "is_income": False},
    {"name": "EMI & Loans", "icon": "🏦", "color": "#ef4444", "is_income": False},
    {"name": "Health & Medical", "icon": "🏥", "color": "#14b8a6", "is_income": False},
    {"name": "Education", "icon": "📚", "color": "#6366f1", "is_income": False},
    {"name": "Entertainment", "icon": "🎬", "color": "#f97316", "is_income": False},
    {"name": "Rent & Housing", "icon": "🏠", "color": "#a855f7", "is_income": False},
    {"name": "Insurance", "icon": "🛡", "color": "#0ea5e9", "is_income": False},
    {"name": "Investment", "icon": "📈", "color": "#c9a55c", "is_income": False},
    {"name": "Transfer", "icon": "↔", "color": "#6b7280", "is_income": False},
    {"name": "Salary", "icon": "💰", "color": "#22c55e", "is_income": True},
    {"name": "Interest & Dividends", "icon": "🏛", "color": "#0d9488", "is_income": True},
    {"name": "Other Income", "icon": "💵", "color": "#84cc16", "is_income": True},
    {"name": "Uncategorized", "icon": "❓", "color": "#9ca3af", "is_income": False},
]
