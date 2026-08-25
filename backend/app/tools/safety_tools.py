from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Beneficiary
from app.schemas.agent import PaymentConditions
from app.services.policy_service import evaluate_payment_policy
from app.services.risk_service import calculate_risk


def calculate_risk_tool(db: Session, session_id: str, amount: float, beneficiary: Beneficiary | None) -> dict:
    return calculate_risk(db, session_id, amount, beneficiary)


def policy_check_tool(
    db: Session,
    session_id: str,
    amount: float,
    beneficiary: Beneficiary | None,
    conditions: PaymentConditions,
    risk: dict,
    account_id: int | None = None,
) -> dict:
    return evaluate_payment_policy(db, session_id, amount, beneficiary, conditions, risk, account_id)
