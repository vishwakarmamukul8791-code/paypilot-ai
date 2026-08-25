from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Beneficiary
from app.schemas.agent import PaymentConditions
from app.services.banking_service import daily_transfer_total, get_account


def _money(value: float | Decimal) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def evaluate_payment_policy(
    db: Session,
    session_id: str,
    amount: float | Decimal,
    beneficiary: Beneficiary | None,
    conditions: PaymentConditions,
    risk: dict,
    account_id: int | None = None,
) -> dict:
    amount_d = _money(amount)
    account = get_account(db, session_id, account_id)
    checks: list[dict] = []

    def check(name: str, passed: bool, detail: str):
        checks.append({"name": name, "passed": passed, "detail": detail})

    check("account_active", account.is_active, "Source account must be active")
    check("beneficiary_verified", bool(beneficiary and beneficiary.verified), "Beneficiary must be registered and verified")
    check("positive_amount", amount_d > 0, "Amount must be greater than zero")
    check(
        "platform_amount_limit",
        amount_d <= settings.max_transfer_amount,
        f"Per-payment demo limit is ₹{settings.max_transfer_amount:,.0f}",
    )
    check("sufficient_balance", account.balance >= amount_d, f"Available balance is ₹{account.balance:,.2f}")
    spent_today = daily_transfer_total(db, session_id, account.id)
    check(
        "daily_limit",
        spent_today + amount_d <= account.daily_limit,
        f"₹{spent_today:,.2f} already transferred today from {account.nickname}; daily limit ₹{account.daily_limit:,.2f}",
    )
    if conditions.minimum_remaining_balance is not None:
        floor = _money(conditions.minimum_remaining_balance)
        remaining = account.balance - amount_d
        check(
            "user_minimum_balance",
            remaining >= floor,
            f"Remaining ₹{remaining:,.2f}; requested floor ₹{floor:,.2f}",
        )
    check(
        "risk_threshold",
        risk["score"] < settings.high_risk_block_score,
        f"Risk score {risk['score']}; block threshold {settings.high_risk_block_score}",
    )

    passed = all(c["passed"] for c in checks)
    return {
        "passed": passed,
        "checks": checks,
        "remaining_balance": round(float(account.balance - amount_d), 2),
        "account_id": account.id,
        "account_nickname": account.nickname,
    }
