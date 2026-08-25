from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Account, Beneficiary, Bill, Transaction

ZERO = Decimal("0.00")


def list_accounts(db: Session, session_id: str, *, active_only: bool = False) -> list[Account]:
    stmt = select(Account).where(Account.session_id == session_id)
    if active_only:
        stmt = stmt.where(Account.is_active.is_(True))
    stmt = stmt.order_by(Account.is_primary.desc(), Account.created_at, Account.id)
    return list(db.scalars(stmt))


def get_account(db: Session, session_id: str, account_id: int | None = None, *, require_active: bool = True) -> Account:
    if account_id is not None:
        account = db.scalar(select(Account).where(Account.session_id == session_id, Account.id == account_id))
    else:
        account = db.scalar(
            select(Account)
            .where(Account.session_id == session_id, Account.is_primary.is_(True))
            .order_by(Account.id)
        )
        if account is None:
            account = db.scalar(select(Account).where(Account.session_id == session_id).order_by(Account.id))
    if not account:
        raise ValueError("Simulation account is not configured")
    if require_active and not account.is_active:
        raise ValueError("Selected simulation account is paused")
    return account


def find_beneficiary(db: Session, session_id: str, name: str | None) -> Beneficiary | None:
    if not name:
        return None
    return db.scalar(
        select(Beneficiary).where(
            Beneficiary.session_id == session_id,
            func.lower(Beneficiary.name) == name.strip().lower(),
        )
    )


def find_bill(db: Session, session_id: str, provider: str | None) -> Bill | None:
    bills = list(db.scalars(select(Bill).where(Bill.session_id == session_id, Bill.status == "PENDING")))
    if provider:
        lowered = provider.lower().strip()
        return next((b for b in bills if b.provider.lower() == lowered), None)
    return bills[0] if len(bills) == 1 else None


def daily_transfer_total(db: Session, session_id: str, account_id: int | None = None) -> Decimal:
    today = datetime.now(timezone.utc).date()
    stmt = select(Transaction).where(
        Transaction.session_id == session_id,
        Transaction.direction == "DEBIT",
        Transaction.status == "COMPLETED",
        Transaction.category != "internal_transfer",
    )
    if account_id is not None:
        stmt = stmt.where(Transaction.account_id == account_id)
    txns = list(db.scalars(stmt))
    return sum((t.amount for t in txns if t.created_at.date() == today), start=ZERO)


def monthly_spending(db: Session, session_id: str, account_id: int | None = None) -> Decimal:
    now = datetime.now(timezone.utc)
    stmt = select(Transaction).where(
        Transaction.session_id == session_id,
        Transaction.direction == "DEBIT",
        Transaction.status == "COMPLETED",
        Transaction.category != "internal_transfer",
    )
    if account_id is not None:
        stmt = stmt.where(Transaction.account_id == account_id)
    txns = list(db.scalars(stmt))
    return sum(
        (t.amount for t in txns if t.created_at.year == now.year and t.created_at.month == now.month),
        start=ZERO,
    )


def debit_history(db: Session, session_id: str, account_id: int | None = None) -> list[Transaction]:
    stmt = select(Transaction).where(
        Transaction.session_id == session_id,
        Transaction.direction == "DEBIT",
        Transaction.status == "COMPLETED",
    )
    if account_id is not None:
        stmt = stmt.where(Transaction.account_id == account_id)
    return list(db.scalars(stmt))


def monthly_debit_history(db: Session, session_id: str, account_id: int | None = None) -> list[Transaction]:
    now = datetime.now(timezone.utc)
    return [
        t
        for t in debit_history(db, session_id, account_id)
        if t.created_at.year == now.year and t.created_at.month == now.month
    ]
