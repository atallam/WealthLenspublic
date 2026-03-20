"""
WealthLens OSS — Bank Statement Parser (multi-source)

Supported formats:
  1. HDFC Bank CSV (savings/current account)
  2. SBI CSV (account statement)
  3. ICICI Bank CSV
  4. Axis Bank CSV
  5. Kotak Mahindra CSV
  6. Generic CSV (auto-detect columns)
  7. Credit card CSV (generic)

Each parser returns a standardized list:
  [{date, description, amount, type (debit/credit), balance, reference, merchant}]

Detection strategy:
  - Try header-based detection first (column names → bank format)
  - Fall back to generic CSV parser
  - AI categorization runs after parsing
"""

import csv
import io
import re
from datetime import datetime
from typing import Optional


def parse_statement(content: str, source_hint: str = "auto") -> dict:
    """
    Parse a bank statement CSV. Returns:
    {
      "source": "hdfc_csv" | "sbi_csv" | ...,
      "transactions": [{date, description, amount, type, balance, reference, merchant}],
      "date_range": {start, end},
      "summary": {total_debit, total_credit, count}
    }
    """
    if source_hint != "auto":
        parser = PARSERS.get(source_hint)
        if parser:
            return parser(content)

    # Auto-detect by header patterns
    first_lines = content[:2000].lower()

    if "hdfc" in first_lines or "narration" in first_lines and "chq./ref.no" in first_lines:
        return parse_hdfc_csv(content)
    elif "sbi" in first_lines or ("txn date" in first_lines and "value date" in first_lines and "branch" in first_lines):
        return parse_sbi_csv(content)
    elif "icici" in first_lines or ("transaction date" in first_lines and "cr/dr" in first_lines):
        return parse_icici_csv(content)
    elif "axis" in first_lines or ("tran date" in first_lines and "particulars" in first_lines):
        return parse_axis_csv(content)
    elif "kotak" in first_lines:
        return parse_kotak_csv(content)

    # Generic fallback
    return parse_generic_csv(content)


# ═══════════════════════════════════════════════════════
# HDFC Bank CSV
# Columns: Date, Narration, Chq./Ref.No., Value Dt, Withdrawal Amt., Deposit Amt., Closing Balance
# ═══════════════════════════════════════════════════════

def parse_hdfc_csv(content: str) -> dict:
    txns = []
    reader = csv.reader(io.StringIO(content))
    header_found = False

    for row in reader:
        if not row or len(row) < 5:
            continue

        # Find header row
        if not header_found:
            joined = " ".join(row).lower()
            if "narration" in joined or "withdrawal" in joined:
                header_found = True
                continue
            continue

        try:
            date_str = row[0].strip()
            if not date_str or not any(c.isdigit() for c in date_str):
                continue

            date = _parse_date(date_str)
            if not date:
                continue

            narration = row[1].strip() if len(row) > 1 else ""
            ref = row[2].strip() if len(row) > 2 else ""
            withdrawal = _parse_amount(row[4]) if len(row) > 4 else 0
            deposit = _parse_amount(row[5]) if len(row) > 5 else 0
            balance = _parse_amount(row[6]) if len(row) > 6 else 0

            amount = withdrawal or deposit
            txn_type = "debit" if withdrawal > 0 else "credit"

            txns.append({
                "date": date, "description": narration,
                "amount": amount, "type": txn_type,
                "balance": balance, "reference": ref,
                "merchant": _extract_merchant(narration),
            })
        except (IndexError, ValueError):
            continue

    return _build_result("hdfc_csv", txns)


# ═══════════════════════════════════════════════════════
# SBI CSV
# Columns: Txn Date, Value Date, Description, Ref No./Cheque No., Branch Code, Debit, Credit, Balance
# ═══════════════════════════════════════════════════════

def parse_sbi_csv(content: str) -> dict:
    txns = []
    reader = csv.reader(io.StringIO(content))
    header_found = False

    for row in reader:
        if not row or len(row) < 6:
            continue

        if not header_found:
            joined = " ".join(row).lower()
            if "txn date" in joined or "description" in joined:
                header_found = True
                continue
            continue

        try:
            date = _parse_date(row[0].strip())
            if not date:
                continue

            desc = row[2].strip() if len(row) > 2 else ""
            ref = row[3].strip() if len(row) > 3 else ""
            debit = _parse_amount(row[5]) if len(row) > 5 else 0
            credit = _parse_amount(row[6]) if len(row) > 6 else 0
            balance = _parse_amount(row[7]) if len(row) > 7 else 0

            amount = debit or credit
            txn_type = "debit" if debit > 0 else "credit"

            txns.append({
                "date": date, "description": desc,
                "amount": amount, "type": txn_type,
                "balance": balance, "reference": ref,
                "merchant": _extract_merchant(desc),
            })
        except (IndexError, ValueError):
            continue

    return _build_result("sbi_csv", txns)


# ═══════════════════════════════════════════════════════
# ICICI Bank CSV
# Columns: S No., Value Date, Transaction Date, Cheque Number, Transaction Remarks, Withdrawal Amount (INR), Deposit Amount (INR), Balance (INR)
# or: Transaction Date, Value Date, Description, Ref No, Debit, Credit, Balance, Cr/Dr
# ═══════════════════════════════════════════════════════

def parse_icici_csv(content: str) -> dict:
    txns = []
    reader = csv.reader(io.StringIO(content))
    header_found = False
    col_map = {}

    for row in reader:
        if not row or len(row) < 5:
            continue

        if not header_found:
            joined = " ".join(row).lower()
            if "transaction" in joined and ("date" in joined or "remarks" in joined):
                header_found = True
                for i, col in enumerate(row):
                    cl = col.strip().lower()
                    if "transaction date" in cl or "txn date" in cl:
                        col_map["date"] = i
                    elif "remark" in cl or "description" in cl:
                        col_map["desc"] = i
                    elif "withdrawal" in cl or "debit" in cl:
                        col_map["debit"] = i
                    elif "deposit" in cl or "credit" in cl:
                        col_map["credit"] = i
                    elif "balance" in cl:
                        col_map["balance"] = i
                    elif "cheque" in cl or "ref" in cl:
                        col_map["ref"] = i
                continue
            continue

        try:
            date = _parse_date(row[col_map.get("date", 0)].strip())
            if not date:
                continue

            desc = row[col_map.get("desc", 1)].strip()
            debit = _parse_amount(row[col_map.get("debit", 4)]) if "debit" in col_map else 0
            credit = _parse_amount(row[col_map.get("credit", 5)]) if "credit" in col_map else 0
            balance = _parse_amount(row[col_map.get("balance", 6)]) if "balance" in col_map else 0
            ref = row[col_map.get("ref", 3)].strip() if "ref" in col_map else ""

            amount = debit or credit
            txn_type = "debit" if debit > 0 else "credit"

            txns.append({
                "date": date, "description": desc,
                "amount": amount, "type": txn_type,
                "balance": balance, "reference": ref,
                "merchant": _extract_merchant(desc),
            })
        except (IndexError, ValueError):
            continue

    return _build_result("icici_csv", txns)


# ═══════════════════════════════════════════════════════
# Axis Bank CSV
# Columns: Tran Date, CHQNO, PARTICULARS, DR, CR, BAL, SOL
# ═══════════════════════════════════════════════════════

def parse_axis_csv(content: str) -> dict:
    txns = []
    reader = csv.reader(io.StringIO(content))
    header_found = False

    for row in reader:
        if not row or len(row) < 5:
            continue

        if not header_found:
            joined = " ".join(row).lower()
            if "tran date" in joined or "particulars" in joined:
                header_found = True
                continue
            continue

        try:
            date = _parse_date(row[0].strip())
            if not date:
                continue

            desc = row[2].strip() if len(row) > 2 else ""
            debit = _parse_amount(row[3]) if len(row) > 3 else 0
            credit = _parse_amount(row[4]) if len(row) > 4 else 0
            balance = _parse_amount(row[5]) if len(row) > 5 else 0

            amount = debit or credit
            txn_type = "debit" if debit > 0 else "credit"

            txns.append({
                "date": date, "description": desc,
                "amount": amount, "type": txn_type,
                "balance": balance, "reference": row[1].strip() if len(row) > 1 else "",
                "merchant": _extract_merchant(desc),
            })
        except (IndexError, ValueError):
            continue

    return _build_result("axis_csv", txns)


# ═══════════════════════════════════════════════════════
# Kotak Mahindra CSV
# ═══════════════════════════════════════════════════════

def parse_kotak_csv(content: str) -> dict:
    # Kotak format similar to HDFC
    return parse_generic_csv(content, source="kotak_csv")


# ═══════════════════════════════════════════════════════
# Generic CSV (auto-detect columns)
# ═══════════════════════════════════════════════════════

def parse_generic_csv(content: str, source: str = "generic_csv") -> dict:
    """Auto-detect column meanings from headers."""
    txns = []
    reader = csv.reader(io.StringIO(content))
    header = None
    col_map = {}

    for row in reader:
        if not row or len(row) < 3:
            continue

        # First non-empty row with text is likely header
        if header is None:
            if any(c.isalpha() for cell in row for c in cell):
                header = [c.strip().lower() for c in row]
                for i, h in enumerate(header):
                    if any(k in h for k in ["date", "txn", "transaction", "posted"]):
                        col_map["date"] = i
                    elif any(k in h for k in ["description", "narration", "particular", "detail", "remark", "memo"]):
                        col_map["desc"] = i
                    elif any(k in h for k in ["withdrawal", "debit", "dr"]):
                        col_map["debit"] = i
                    elif any(k in h for k in ["deposit", "credit", "cr"]):
                        col_map["credit"] = i
                    elif any(k in h for k in ["amount"]):
                        col_map["amount"] = i
                    elif any(k in h for k in ["balance", "closing"]):
                        col_map["balance"] = i
                    elif any(k in h for k in ["ref", "cheque", "chq", "reference"]):
                        col_map["ref"] = i
                    elif any(k in h for k in ["type", "cr/dr", "dr/cr"]):
                        col_map["type_col"] = i
                continue

            continue

        try:
            date_idx = col_map.get("date", 0)
            date = _parse_date(row[date_idx].strip())
            if not date:
                continue

            desc = row[col_map.get("desc", 1)].strip() if "desc" in col_map else ""

            # Handle amount vs debit/credit columns
            if "amount" in col_map and "debit" not in col_map:
                amount = _parse_amount(row[col_map["amount"]])
                if "type_col" in col_map:
                    type_val = row[col_map["type_col"]].strip().lower()
                    txn_type = "credit" if type_val in ("cr", "credit", "c") else "debit"
                else:
                    txn_type = "credit" if amount > 0 else "debit"
                    amount = abs(amount)
            else:
                debit = _parse_amount(row[col_map.get("debit", 2)]) if "debit" in col_map else 0
                credit = _parse_amount(row[col_map.get("credit", 3)]) if "credit" in col_map else 0
                amount = debit or credit
                txn_type = "debit" if debit > 0 else "credit"

            balance = _parse_amount(row[col_map.get("balance", -1)]) if "balance" in col_map else 0
            ref = row[col_map.get("ref", 0)].strip() if "ref" in col_map else ""

            if amount > 0:
                txns.append({
                    "date": date, "description": desc,
                    "amount": amount, "type": txn_type,
                    "balance": balance, "reference": ref,
                    "merchant": _extract_merchant(desc),
                })
        except (IndexError, ValueError):
            continue

    return _build_result(source, txns)


# ═══════════════════════════════════════════════════════
# AI-Powered Transaction Categorization
# ═══════════════════════════════════════════════════════

def categorize_transactions(transactions: list[dict], categories: list[dict]) -> list[dict]:
    """
    Rule-based categorization with keyword matching.
    Falls back to "Uncategorized" for unknown transactions.
    AI categorization is available as a separate endpoint.
    """
    cat_map = {c["name"]: c["id"] for c in categories}
    rules = _build_category_rules(categories)

    for txn in transactions:
        desc = (txn.get("description", "") + " " + txn.get("merchant", "")).lower()
        txn["category_id"] = None
        txn["category_name"] = "Uncategorized"

        for cat_name, keywords in rules.items():
            if any(kw in desc for kw in keywords):
                txn["category_id"] = cat_map.get(cat_name)
                txn["category_name"] = cat_name
                break

        if not txn["category_id"] and txn["type"] == "credit":
            if any(kw in desc for kw in ["salary", "sal cr", "payroll", "stipend"]):
                txn["category_id"] = cat_map.get("Salary")
                txn["category_name"] = "Salary"
            elif any(kw in desc for kw in ["interest", "int.cr", "dividend", "div"]):
                txn["category_id"] = cat_map.get("Interest & Dividends")
                txn["category_name"] = "Interest & Dividends"

    return transactions


def _build_category_rules(categories: list[dict]) -> dict:
    """Keyword rules for auto-categorization."""
    return {
        "Groceries": ["bigbasket", "blinkit", "zepto", "dmart", "more ", "grofers", "jiomart", "grocery", "supermarket", "reliance fresh", "big bazaar", "nature basket", "spencer"],
        "Dining & Food": ["swiggy", "zomato", "uber eats", "dominos", "mcdonald", "starbucks", "cafe", "restaurant", "pizza", "kfc", "burger", "food", "dunkin"],
        "Transport": ["uber", "ola", "rapido", "metro", "petrol", "diesel", "fuel", "parking", "toll", "fastag", "irctc", "railway", "redbus", "flight", "makemytrip", "cleartrip"],
        "Shopping": ["amazon", "flipkart", "myntra", "ajio", "nykaa", "tatacliq", "meesho", "snapdeal", "shopping", "croma", "reliance digital", "apple.com"],
        "Utilities & Bills": ["electricity", "water bill", "gas bill", "broadband", "wifi", "airtel", "jio", "vodafone", "bsnl", "dth", "tata sky", "mobile recharge", "postpaid"],
        "EMI & Loans": ["emi", "loan", "neft-loan", "home loan", "car loan", "personal loan", "bajaj fin", "hdfc ltd", "lic housing"],
        "Health & Medical": ["hospital", "pharmacy", "medical", "doctor", "apollo", "medplus", "1mg", "pharmeasy", "netmeds", "practo", "health", "diagnostic"],
        "Education": ["school", "college", "university", "tuition", "coaching", "udemy", "coursera", "byju", "unacademy", "edx", "book"],
        "Entertainment": ["netflix", "hotstar", "prime video", "spotify", "youtube", "cinema", "movie", "pvr", "inox", "bookmyshow", "game", "playstation", "xbox"],
        "Rent & Housing": ["rent", "house rent", "maintenance", "society", "housing"],
        "Insurance": ["insurance", "premium", "lic", "hdfc life", "icici pru", "star health", "policy"],
        "Investment": ["mutual fund", "sip", "zerodha", "groww", "upstox", "kuvera", "coin", "nps", "ppf deposit", "stock", "share"],
        "Transfer": ["neft", "rtgs", "imps", "upi", "transfer", "self transfer", "fund transfer"],
    }


# ═══════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════

DATE_FORMATS = [
    "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y",
    "%Y-%m-%d", "%Y/%m/%d",
    "%d %b %Y", "%d-%b-%Y", "%d %b %y", "%d-%b-%y",
    "%d %B %Y", "%m/%d/%Y",
]


def _parse_date(s: str) -> Optional[str]:
    """Try multiple date formats, return YYYY-MM-DD or None."""
    s = s.strip().replace("  ", " ")
    if not s:
        return None
    for fmt in DATE_FORMATS:
        try:
            dt = datetime.strptime(s, fmt)
            if dt.year < 100:
                dt = dt.replace(year=dt.year + 2000)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _parse_amount(s) -> float:
    """Parse amount string, handling Indian number formatting."""
    if not s:
        return 0
    s = str(s).strip()
    if not s or s == "-" or s.lower() in ("null", "none", ""):
        return 0
    # Remove commas, spaces, currency symbols
    s = re.sub(r"[₹$,\s]", "", s)
    s = s.replace("(", "-").replace(")", "")  # Negative amounts
    try:
        return abs(float(s))
    except ValueError:
        return 0


def _extract_merchant(description: str) -> str:
    """Extract merchant name from transaction description."""
    desc = description.upper()
    # UPI format: UPI-MERCHANT NAME-VPA
    upi_match = re.search(r"UPI[-/]([A-Z0-9\s]+?)[-/]", desc)
    if upi_match:
        return upi_match.group(1).strip().title()

    # NEFT/IMPS format: NEFT-NAME or IMPS-NAME
    neft_match = re.search(r"(?:NEFT|IMPS|RTGS)[-/]([A-Z0-9\s]+?)[-/]", desc)
    if neft_match:
        return neft_match.group(1).strip().title()

    # POS/Card: POS MERCHANT NAME
    pos_match = re.search(r"POS\s+(.+?)(?:\s+\d|$)", desc)
    if pos_match:
        return pos_match.group(1).strip().title()

    # Fallback: first meaningful words
    words = description.split()
    if len(words) > 2:
        return " ".join(words[:3]).title()
    return description.strip().title()


def _build_result(source: str, txns: list[dict]) -> dict:
    """Build standardized result from parsed transactions."""
    total_debit = sum(t["amount"] for t in txns if t["type"] == "debit")
    total_credit = sum(t["amount"] for t in txns if t["type"] == "credit")
    dates = [t["date"] for t in txns if t["date"]]

    return {
        "source": source,
        "transactions": txns,
        "date_range": {
            "start": min(dates) if dates else None,
            "end": max(dates) if dates else None,
        },
        "summary": {
            "total_debit": round(total_debit, 2),
            "total_credit": round(total_credit, 2),
            "count": len(txns),
        },
    }


PARSERS = {
    "hdfc_csv": parse_hdfc_csv,
    "sbi_csv": parse_sbi_csv,
    "icici_csv": parse_icici_csv,
    "axis_csv": parse_axis_csv,
    "kotak_csv": parse_kotak_csv,
    "generic_csv": parse_generic_csv,
}
