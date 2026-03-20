"""
WealthLens OSS — Budget Routes

POST   /api/budget/import              — upload bank statement (CSV)
GET    /api/budget/imports              — list import history (1 year)
DELETE /api/budget/imports/{id}         — delete an import + its transactions
GET    /api/budget/transactions         — list transactions (month filter)
PUT    /api/budget/transactions/{id}    — update category of a transaction
POST   /api/budget/transactions/manual  — add manual transaction
DELETE /api/budget/transactions/{id}    — delete transaction
GET    /api/budget/categories           — list categories
POST   /api/budget/categories           — create category
PUT    /api/budget/categories/{id}      — update category
DELETE /api/budget/categories/{id}      — delete category
GET    /api/budget/buckets              — list budget buckets (month filter)
POST   /api/budget/buckets              — set budget for category+month
PUT    /api/budget/buckets/{id}         — update budget limit
DELETE /api/budget/buckets/{id}         — delete budget
GET    /api/budget/summary/{month}      — monthly summary (for charts)
POST   /api/budget/categorize-ai       — AI-powered re-categorization
"""

from datetime import datetime, date, timedelta
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user, AuthContext
from app.budget_models import (
    BudgetImport, BudgetTransaction, BudgetCategory, BudgetBucket,
    DEFAULT_CATEGORIES
)
from app.encryption import encrypt_json, decrypt_json
from app.services.statement_parser import parse_statement, categorize_transactions
from app.models import gen_id

router = APIRouter(prefix="/api/budget", tags=["budget"])


# ─── Schemas ───

class ManualTxnRequest(BaseModel):
    date: str  # YYYY-MM-DD
    description: str
    amount: float
    type: str  # debit | credit
    category_id: Optional[str] = None

class UpdateTxnCategory(BaseModel):
    category_id: str

class CategoryCreate(BaseModel):
    name: str
    icon: Optional[str] = ""
    color: Optional[str] = "#6b7280"
    is_income: Optional[bool] = False

class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None

class BucketCreate(BaseModel):
    category_id: str
    month: str  # YYYY-MM
    budget_limit: float

class BucketUpdate(BaseModel):
    budget_limit: float


# ─── Statement Import ───

@router.post("/import")
async def import_statement(
    file: UploadFile = File(...),
    source_hint: str = Form("auto"),
    source_name: str = Form(""),
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload and parse a bank statement CSV."""
    content = (await file.read()).decode("utf-8", errors="ignore")
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 5MB)")

    # Ensure categories exist
    _ensure_default_categories(db, auth.user_id)

    # Parse the statement
    result = parse_statement(content, source_hint)
    if not result["transactions"]:
        raise HTTPException(status_code=400, detail="No transactions found. Check format or try a different source hint.")

    # Get user's categories for auto-categorization
    cats = db.query(BudgetCategory).filter(BudgetCategory.user_id == auth.user_id).all()
    cat_list = [{"id": c.id, "name": c.name} for c in cats]
    uncat_id = next((c.id for c in cats if c.name == "Uncategorized"), None)

    # Auto-categorize
    categorized = categorize_transactions(result["transactions"], cat_list)

    # Create import record
    dr = result["date_range"]
    imp = BudgetImport(
        user_id=auth.user_id,
        source_type=result["source"],
        source_name=source_name or result["source"],
        file_name=file.filename or "statement.csv",
        status="completed",
        transaction_count=len(categorized),
        date_range_start=datetime.strptime(dr["start"], "%Y-%m-%d").date() if dr["start"] else None,
        date_range_end=datetime.strptime(dr["end"], "%Y-%m-%d").date() if dr["end"] else None,
        encrypted_summary=encrypt_json(result["summary"], auth.dek),
        expires_at=datetime.utcnow() + timedelta(days=365),  # 1 year retention
    )
    db.add(imp)
    db.flush()

    # Create encrypted transaction records
    for txn in categorized:
        txn_date = datetime.strptime(txn["date"], "%Y-%m-%d").date()
        sensitive = {
            "description": txn["description"],
            "amount": txn["amount"],
            "balance": txn.get("balance", 0),
            "merchant": txn.get("merchant", ""),
            "reference": txn.get("reference", ""),
        }
        bt = BudgetTransaction(
            user_id=auth.user_id,
            import_id=imp.id,
            txn_date=txn_date,
            txn_month=txn_date.strftime("%Y-%m"),
            txn_type=txn["type"],
            category_id=txn.get("category_id") or uncat_id,
            source_type=result["source"],
            encrypted_data=encrypt_json(sensitive, auth.dek),
        )
        db.add(bt)

    db.commit()

    return {
        "import_id": imp.id,
        "source": result["source"],
        "transactions_imported": len(categorized),
        "date_range": dr,
        "summary": result["summary"],
    }


@router.get("/imports")
def list_imports(
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List import history (past 1 year)."""
    cutoff = datetime.utcnow() - timedelta(days=365)
    imports = (
        db.query(BudgetImport)
        .filter(BudgetImport.user_id == auth.user_id, BudgetImport.created_at >= cutoff)
        .order_by(BudgetImport.created_at.desc())
        .all()
    )
    result = []
    for imp in imports:
        summary = {}
        if imp.encrypted_summary:
            try:
                summary = decrypt_json(imp.encrypted_summary, auth.dek)
            except Exception:
                pass

        result.append({
            "id": imp.id,
            "source_type": imp.source_type,
            "source_name": imp.source_name,
            "file_name": imp.file_name,
            "status": imp.status,
            "transaction_count": imp.transaction_count,
            "date_range_start": imp.date_range_start.isoformat() if imp.date_range_start else None,
            "date_range_end": imp.date_range_end.isoformat() if imp.date_range_end else None,
            "summary": summary,
            "created_at": imp.created_at.isoformat() if imp.created_at else None,
        })
    return result


@router.delete("/imports/{import_id}")
def delete_import(
    import_id: str,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    imp = db.query(BudgetImport).filter(
        BudgetImport.id == import_id, BudgetImport.user_id == auth.user_id
    ).first()
    if not imp:
        raise HTTPException(status_code=404, detail="Import not found")
    db.delete(imp)  # CASCADE deletes transactions
    db.commit()
    return {"message": "Import and transactions deleted"}


# ─── Transactions ───

@router.get("/transactions")
def list_transactions(
    month: Optional[str] = None,  # YYYY-MM
    category_id: Optional[str] = None,
    txn_type: Optional[str] = None,  # debit | credit
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List transactions with optional filters."""
    query = db.query(BudgetTransaction).filter(BudgetTransaction.user_id == auth.user_id)

    if month:
        query = query.filter(BudgetTransaction.txn_month == month)
    if category_id:
        query = query.filter(BudgetTransaction.category_id == category_id)
    if txn_type:
        query = query.filter(BudgetTransaction.txn_type == txn_type)

    txns = query.order_by(BudgetTransaction.txn_date.desc()).limit(500).all()

    result = []
    for t in txns:
        try:
            data = decrypt_json(t.encrypted_data, auth.dek)
        except Exception:
            continue
        result.append({
            "id": t.id,
            "date": t.txn_date.isoformat() if t.txn_date else "",
            "month": t.txn_month,
            "type": t.txn_type,
            "category_id": t.category_id,
            "source": t.source_type,
            "import_id": t.import_id,
            **data,
        })
    return result


@router.put("/transactions/{txn_id}")
def update_transaction_category(
    txn_id: str, req: UpdateTxnCategory,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    txn = db.query(BudgetTransaction).filter(
        BudgetTransaction.id == txn_id, BudgetTransaction.user_id == auth.user_id
    ).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    txn.category_id = req.category_id
    db.commit()
    return {"message": "Category updated"}


@router.post("/transactions/manual")
def add_manual_transaction(
    req: ManualTxnRequest,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_default_categories(db, auth.user_id)
    txn_date = datetime.strptime(req.date, "%Y-%m-%d").date()

    sensitive = {
        "description": req.description,
        "amount": req.amount,
        "balance": 0,
        "merchant": "",
        "reference": "",
    }
    bt = BudgetTransaction(
        user_id=auth.user_id,
        txn_date=txn_date,
        txn_month=txn_date.strftime("%Y-%m"),
        txn_type=req.type,
        category_id=req.category_id,
        source_type="manual",
        encrypted_data=encrypt_json(sensitive, auth.dek),
    )
    db.add(bt)
    db.commit()
    return {"id": bt.id, "message": "Transaction added"}


@router.delete("/transactions/{txn_id}")
def delete_transaction(
    txn_id: str,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    txn = db.query(BudgetTransaction).filter(
        BudgetTransaction.id == txn_id, BudgetTransaction.user_id == auth.user_id
    ).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    db.delete(txn)
    db.commit()
    return {"message": "Deleted"}


# ─── Categories ───

@router.get("/categories")
def list_categories(
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_default_categories(db, auth.user_id)
    cats = (
        db.query(BudgetCategory)
        .filter(BudgetCategory.user_id == auth.user_id)
        .order_by(BudgetCategory.sort_order, BudgetCategory.name)
        .all()
    )
    return [{
        "id": c.id, "name": c.name, "icon": c.icon, "color": c.color,
        "is_income": c.is_income, "is_system": c.is_system, "sort_order": c.sort_order,
    } for c in cats]


@router.post("/categories", status_code=201)
def create_category(
    req: CategoryCreate,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cat = BudgetCategory(
        user_id=auth.user_id, name=req.name, icon=req.icon,
        color=req.color, is_income=req.is_income,
    )
    db.add(cat)
    db.commit()
    return {"id": cat.id, "name": cat.name}


@router.put("/categories/{cat_id}")
def update_category(
    cat_id: str, req: CategoryUpdate,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cat = db.query(BudgetCategory).filter(
        BudgetCategory.id == cat_id, BudgetCategory.user_id == auth.user_id
    ).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    if req.name is not None: cat.name = req.name
    if req.icon is not None: cat.icon = req.icon
    if req.color is not None: cat.color = req.color
    db.commit()
    return {"message": "Updated"}


@router.delete("/categories/{cat_id}")
def delete_category(
    cat_id: str,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cat = db.query(BudgetCategory).filter(
        BudgetCategory.id == cat_id, BudgetCategory.user_id == auth.user_id
    ).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    # Move transactions to Uncategorized instead of deleting
    uncat = db.query(BudgetCategory).filter(
        BudgetCategory.user_id == auth.user_id, BudgetCategory.name == "Uncategorized"
    ).first()
    if uncat:
        db.query(BudgetTransaction).filter(
            BudgetTransaction.category_id == cat_id
        ).update({"category_id": uncat.id})
    db.delete(cat)
    db.commit()
    return {"message": "Category deleted, transactions moved to Uncategorized"}


# ─── Budget Buckets ───

@router.get("/buckets")
def list_buckets(
    month: Optional[str] = None,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(BudgetBucket).filter(BudgetBucket.user_id == auth.user_id)
    if month:
        query = query.filter(BudgetBucket.month == month)
    buckets = query.all()
    return [{
        "id": b.id, "category_id": b.category_id, "month": b.month,
        "budget_limit": b.budget_limit, "notes": b.notes,
    } for b in buckets]


@router.post("/buckets", status_code=201)
def create_bucket(
    req: BucketCreate,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Check if bucket already exists for this category+month
    existing = db.query(BudgetBucket).filter(
        BudgetBucket.user_id == auth.user_id,
        BudgetBucket.category_id == req.category_id,
        BudgetBucket.month == req.month,
    ).first()
    if existing:
        existing.budget_limit = req.budget_limit
        db.commit()
        return {"id": existing.id, "message": "Budget updated"}

    bucket = BudgetBucket(
        user_id=auth.user_id,
        category_id=req.category_id,
        month=req.month,
        budget_limit=req.budget_limit,
    )
    db.add(bucket)
    db.commit()
    return {"id": bucket.id, "message": "Budget set"}


@router.put("/buckets/{bucket_id}")
def update_bucket(
    bucket_id: str, req: BucketUpdate,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bucket = db.query(BudgetBucket).filter(
        BudgetBucket.id == bucket_id, BudgetBucket.user_id == auth.user_id
    ).first()
    if not bucket:
        raise HTTPException(status_code=404, detail="Budget not found")
    bucket.budget_limit = req.budget_limit
    db.commit()
    return {"message": "Updated"}


@router.delete("/buckets/{bucket_id}")
def delete_bucket(
    bucket_id: str,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bucket = db.query(BudgetBucket).filter(
        BudgetBucket.id == bucket_id, BudgetBucket.user_id == auth.user_id
    ).first()
    if not bucket:
        raise HTTPException(status_code=404, detail="Budget not found")
    db.delete(bucket)
    db.commit()
    return {"message": "Deleted"}


# ─── Monthly Summary (for charts) ───

@router.get("/summary/{month}")
def monthly_summary(
    month: str,  # YYYY-MM
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Monthly spending summary — category totals, budget vs actual, trends.
    This is the data source for pie charts and bar graphs.
    """
    _ensure_default_categories(db, auth.user_id)

    # Get all transactions for this month
    txns = (
        db.query(BudgetTransaction)
        .filter(BudgetTransaction.user_id == auth.user_id, BudgetTransaction.txn_month == month)
        .all()
    )

    # Get categories
    cats = db.query(BudgetCategory).filter(BudgetCategory.user_id == auth.user_id).all()
    cat_map = {c.id: {"name": c.name, "icon": c.icon, "color": c.color, "is_income": c.is_income} for c in cats}

    # Get budgets for this month
    buckets = db.query(BudgetBucket).filter(
        BudgetBucket.user_id == auth.user_id, BudgetBucket.month == month
    ).all()
    budget_map = {b.category_id: b.budget_limit for b in buckets}

    # Aggregate by category
    by_category = {}
    total_debit = 0
    total_credit = 0

    for t in txns:
        try:
            data = decrypt_json(t.encrypted_data, auth.dek)
        except Exception:
            continue

        amount = data.get("amount", 0)
        cat_id = t.category_id or "uncategorized"

        if t.txn_type == "debit":
            total_debit += amount
        else:
            total_credit += amount

        if cat_id not in by_category:
            cat_info = cat_map.get(cat_id, {"name": "Uncategorized", "icon": "❓", "color": "#9ca3af", "is_income": False})
            by_category[cat_id] = {
                "category_id": cat_id,
                "name": cat_info["name"],
                "icon": cat_info["icon"],
                "color": cat_info["color"],
                "is_income": cat_info["is_income"],
                "total": 0,
                "count": 0,
                "budget": budget_map.get(cat_id, 0),
            }

        by_category[cat_id]["total"] += amount
        by_category[cat_id]["count"] += 1

    # Build response
    categories = sorted(by_category.values(), key=lambda x: x["total"], reverse=True)

    # Previous month for comparison
    try:
        y, m = int(month[:4]), int(month[5:7])
        prev_m = m - 1 if m > 1 else 12
        prev_y = y if m > 1 else y - 1
        prev_month = f"{prev_y:04d}-{prev_m:02d}"
    except (ValueError, IndexError):
        prev_month = None

    prev_total = 0
    if prev_month:
        prev_txns = (
            db.query(BudgetTransaction)
            .filter(BudgetTransaction.user_id == auth.user_id,
                    BudgetTransaction.txn_month == prev_month,
                    BudgetTransaction.txn_type == "debit")
            .all()
        )
        for pt in prev_txns:
            try:
                pd = decrypt_json(pt.encrypted_data, auth.dek)
                prev_total += pd.get("amount", 0)
            except Exception:
                pass

    return {
        "month": month,
        "total_spending": round(total_debit, 2),
        "total_income": round(total_credit, 2),
        "net": round(total_credit - total_debit, 2),
        "transaction_count": len(txns),
        "categories": categories,
        "total_budget": sum(b.budget_limit for b in buckets),
        "budget_utilization": round(total_debit / sum(b.budget_limit for b in buckets) * 100, 1) if buckets and sum(b.budget_limit for b in buckets) > 0 else 0,
        "vs_prev_month": round(total_debit - prev_total, 2) if prev_month else None,
        "vs_prev_month_pct": round((total_debit - prev_total) / prev_total * 100, 1) if prev_total > 0 else None,
    }


# ─── AI Categorization ───

@router.post("/categorize-ai")
async def ai_categorize(
    month: str = "",
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Use Claude to re-categorize uncategorized transactions."""
    from app.config import settings
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(status_code=501, detail="AI not configured")

    # Get uncategorized transactions
    uncat = db.query(BudgetCategory).filter(
        BudgetCategory.user_id == auth.user_id, BudgetCategory.name == "Uncategorized"
    ).first()
    if not uncat:
        return {"recategorized": 0}

    query = db.query(BudgetTransaction).filter(
        BudgetTransaction.user_id == auth.user_id,
        BudgetTransaction.category_id == uncat.id,
    )
    if month:
        query = query.filter(BudgetTransaction.txn_month == month)

    txns = query.limit(50).all()
    if not txns:
        return {"recategorized": 0}

    # Get all categories
    cats = db.query(BudgetCategory).filter(BudgetCategory.user_id == auth.user_id).all()
    cat_names = [c.name for c in cats if c.name != "Uncategorized"]
    cat_id_map = {c.name: c.id for c in cats}

    # Build prompt
    txn_lines = []
    txn_map = {}
    for t in txns:
        try:
            data = decrypt_json(t.encrypted_data, auth.dek)
            desc = data.get("description", "")[:100]
            txn_lines.append(f"{t.id}: {desc}")
            txn_map[t.id] = t
        except Exception:
            pass

    if not txn_lines:
        return {"recategorized": 0}

    prompt = f"""Categorize these Indian bank transactions into ONE of these categories:
{', '.join(cat_names)}

Transactions (ID: description):
{chr(10).join(txn_lines)}

Respond ONLY with JSON: {{"results": [{{"id": "...", "category": "..."}}]}}"""

    import httpx
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": settings.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": "claude-sonnet-4-20250514", "max_tokens": 1000, "messages": [{"role": "user", "content": prompt}]}
            )
            ai_data = resp.json()
            text = "".join(b.get("text", "") for b in ai_data.get("content", []) if b.get("type") == "text")

        import json
        parsed = json.loads(text.strip().replace("```json", "").replace("```", ""))
        count = 0
        for r in parsed.get("results", []):
            tid = r.get("id", "")
            cat_name = r.get("category", "")
            cat_id = cat_id_map.get(cat_name)
            if tid in txn_map and cat_id:
                txn_map[tid].category_id = cat_id
                count += 1

        db.commit()
        return {"recategorized": count}
    except Exception as e:
        return {"recategorized": 0, "error": str(e)}


# ─── Helpers ───

def _ensure_default_categories(db: Session, user_id: str):
    """Create default categories if none exist."""
    existing = db.query(BudgetCategory).filter(BudgetCategory.user_id == user_id).count()
    if existing > 0:
        return

    for i, cat in enumerate(DEFAULT_CATEGORIES):
        db.add(BudgetCategory(
            user_id=user_id, name=cat["name"], icon=cat["icon"],
            color=cat["color"], is_income=cat.get("is_income", False),
            is_system=True, sort_order=i,
        ))
    db.commit()
