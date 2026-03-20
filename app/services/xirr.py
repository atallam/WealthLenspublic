"""
WealthLens OSS — XIRR Calculator (Newton-Raphson)
"""

from datetime import datetime
from typing import Optional
from scipy.optimize import brentq


def compute_xirr(cashflows: list[dict]) -> Optional[float]:
    """
    Compute XIRR (annualized IRR) for a list of cashflows.
    Each cashflow: {"date": "YYYY-MM-DD", "amount": float}
    Negative = money out (buy), Positive = money in (sell / current value).
    Returns annualized rate as a decimal (0.12 = 12%) or None if no convergence.
    """
    if len(cashflows) < 2:
        return None

    # Parse dates
    parsed = []
    for cf in cashflows:
        try:
            d = datetime.strptime(str(cf["date"]), "%Y-%m-%d")
        except (ValueError, KeyError):
            continue
        parsed.append((d, float(cf["amount"])))

    if len(parsed) < 2:
        return None

    # Sort by date
    parsed.sort(key=lambda x: x[0])
    t0 = parsed[0][0]

    # Convert dates to year fractions
    year_fracs = [(d - t0).days / 365.25 for d, _ in parsed]
    amounts = [a for _, a in parsed]

    def npv(rate):
        return sum(a / (1 + rate) ** t for a, t in zip(amounts, year_fracs))

    # Use Brent's method for root finding (more robust than Newton-Raphson)
    try:
        result = brentq(npv, -0.99, 10.0, maxiter=200)
        return round(result, 6)
    except (ValueError, RuntimeError):
        # Try wider range
        try:
            result = brentq(npv, -0.999, 100.0, maxiter=500)
            return round(result, 6)
        except Exception:
            return None
