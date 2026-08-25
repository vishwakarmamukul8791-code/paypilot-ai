from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.banking_service import find_beneficiary, find_bill, get_account, monthly_spending


def get_balance_tool(db: Session, session_id: str, account_id: int | None = None) -> dict:
    account = get_account(db, session_id, account_id)
    return {
        "account_id": account.id,
        "nickname": account.nickname,
        "account_type": account.account_type,
        "balance": float(account.balance),
        "currency": account.currency,
        "masked_account": account.masked_account,
        "daily_limit": float(account.daily_limit),
    }


def find_beneficiary_tool(db: Session, session_id: str, name: str | None) -> dict:
    beneficiary = find_beneficiary(db, session_id, name)
    return {
        "found": bool(beneficiary),
        "name": beneficiary.name if beneficiary else name,
        "verified": bool(beneficiary and beneficiary.verified),
    }


def get_bill_tool(db: Session, session_id: str, provider: str | None) -> dict:
    bill = find_bill(db, session_id, provider)
    return {
        "found": bool(bill),
        "provider": bill.provider if bill else provider,
        "amount": float(bill.amount) if bill else None,
        "status": bill.status if bill else None,
    }


def monthly_spending_tool(db: Session, session_id: str, account_id: int | None = None) -> dict:
    account = get_account(db, session_id, account_id)
    return {
        "monthly_spending": round(float(monthly_spending(db, session_id, account.id)), 2),
        "currency": "INR",
        "account_id": account.id,
        "account_nickname": account.nickname,
    }
