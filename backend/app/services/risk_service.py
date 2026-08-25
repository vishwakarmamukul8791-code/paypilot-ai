from __future__ import annotations

from decimal import Decimal
from sqlalchemy.orm import Session
from app.models import Beneficiary


def _money(value: float | Decimal) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def calculate_risk(db: Session, session_id: str, amount: float | Decimal, beneficiary: Beneficiary | None) -> dict:
    amount_d = _money(amount)
    if amount_d <= Decimal("10000"):
        level, score = "LOW", 20
        reason = "Amount is within the fixed LOW band (up to ₹10,000)"
    elif amount_d <= Decimal("50000"):
        level, score = "MEDIUM", 60
        reason = "Amount is within the fixed MEDIUM band (above ₹10,000 through ₹50,000)"
    else:
        level, score = "HIGH", 90
        reason = "Amount is above ₹50,000 and falls in the fixed HIGH band"
    return {"score": score, "level": level, "reasons": [reason]}
