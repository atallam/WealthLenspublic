"""
WealthLens OSS — Pydantic Schemas
Request/response models for the API.
"""

from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import date


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    display_name: str


class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str


# ---------------------------------------------------------------------------
# Holdings
# ---------------------------------------------------------------------------

class HoldingCreate(BaseModel):
    name: str
    type: str  # FD | PPF | EPF | MF | IN_STOCK | IN_ETF | US_STOCK | REAL_ESTATE
    member_id: str
    ticker: Optional[str] = None
    scheme_code: Optional[str] = None
    purchase_value: Optional[float] = None
    current_value: Optional[float] = None
    principal: Optional[float] = None
    interest_rate: Optional[float] = None
    usd_inr_rate: Optional[float] = None
    start_date: Optional[str] = None
    maturity_date: Optional[str] = None


class HoldingUpdate(BaseModel):
    name: Optional[str] = None
    current_value: Optional[float] = None
    principal: Optional[float] = None
    interest_rate: Optional[float] = None
    usd_inr_rate: Optional[float] = None
    maturity_date: Optional[str] = None


class HoldingResponse(BaseModel):
    id: str
    name: str
    type: str
    member_id: str
    ticker: Optional[str] = None
    scheme_code: Optional[str] = None
    purchase_value: Optional[float] = None
    current_value: Optional[float] = None
    principal: Optional[float] = None
    interest_rate: Optional[float] = None
    usd_inr_rate: Optional[float] = None
    start_date: Optional[str] = None
    maturity_date: Optional[str] = None
    net_units: Optional[float] = None
    avg_cost: Optional[float] = None
    transactions: list = []
    artifacts: list = []


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------

class TransactionCreate(BaseModel):
    holding_id: str
    txn_type: str  # BUY | SELL
    units: float
    price: float
    price_usd: Optional[float] = None
    txn_date: str  # YYYY-MM-DD
    notes: Optional[str] = ""


class TransactionResponse(BaseModel):
    id: str
    holding_id: str
    txn_type: str
    units: float
    price: float
    price_usd: Optional[float] = None
    txn_date: str
    notes: Optional[str] = ""


# ---------------------------------------------------------------------------
# Portfolio (members, goals, alerts)
# ---------------------------------------------------------------------------

class MemberSchema(BaseModel):
    id: str
    name: str
    relation: str


class GoalSchema(BaseModel):
    id: str
    name: str
    targetAmount: float
    targetDate: str
    category: Optional[str] = ""
    color: Optional[str] = "#4f8ef7"
    priority: Optional[int] = 1
    linkedMembers: list[str] = []
    monthlyContrib: Optional[float] = 0
    notes: Optional[str] = ""


class AlertSchema(BaseModel):
    id: str
    type: str  # ALLOCATION_DRIFT | CONCENTRATION | RETURN_TARGET
    assetType: Optional[str] = ""
    threshold: float
    label: str
    active: bool = True


class PortfolioData(BaseModel):
    members: list[MemberSchema] = []
    goals: list[GoalSchema] = []
    alerts: list[AlertSchema] = []


# ---------------------------------------------------------------------------
# Market Data
# ---------------------------------------------------------------------------

class MFSearchResult(BaseModel):
    schemeCode: str
    schemeName: str


class NAVResult(BaseModel):
    nav: float
    nav_date: str
    is_estimated: bool = False


class SIPNavRequest(BaseModel):
    scheme_code: str
    dates: list[dict]  # [{year, month, day}]


class PriceRefreshResponse(BaseModel):
    updated_count: int
    errors: list[str] = []


# ---------------------------------------------------------------------------
# AI Advisor
# ---------------------------------------------------------------------------

class AIMessageRequest(BaseModel):
    messages: list[dict]  # [{role, content}]
    context: Optional[str] = ""


class AIMessageResponse(BaseModel):
    content: str


# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------

class ArtifactResponse(BaseModel):
    id: str
    holding_id: str
    filename: str
    description: Optional[str] = ""
