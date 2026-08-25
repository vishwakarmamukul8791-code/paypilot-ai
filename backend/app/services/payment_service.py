from __future__ import annotations

import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import Account, Bill, PaymentRequest, Transaction
from app.services.banking_service import daily_transfer_total, find_beneficiary, get_account

_lock_guard = threading.Lock()
_session_locks: dict[str, threading.RLock] = {}


@contextmanager
def payment_execution_lock(session_id: str):
    """Serialize state-changing operations for one public demo session in-process."""
    with _lock_guard:
        lock = _session_locks.setdefault(session_id, threading.RLock())
    with lock:
        yield


def begin_serialized_payment_transaction(db: Session, session_id: str, account_id: int | None = None) -> None:
    """Acquire DB-side serialization for the source account before final revalidation."""
    dialect = db.get_bind().dialect.name
    if dialect == "sqlite":
        db.execute(text("BEGIN IMMEDIATE"))
        return

    account = db.scalar(
        select(Account)
        .where(Account.session_id == session_id, Account.id == account_id if account_id is not None else Account.is_primary.is_(True))
        .with_for_update()
    )
    if account is None:
        raise ValueError("Simulation account is not configured")


def begin_serialized_accounts_transaction(db: Session, session_id: str, account_ids: list[int]) -> None:
    """Lock all accounts participating in an internal transfer in stable ID order."""
    ids = sorted(set(account_ids))
    if not ids:
        raise ValueError("At least one account is required")

    dialect = db.get_bind().dialect.name
    if dialect == "sqlite":
        db.execute(text("BEGIN IMMEDIATE"))
        return

    accounts = list(
        db.scalars(
            select(Account)
            .where(Account.session_id == session_id, Account.id.in_(ids))
            .order_by(Account.id)
            .with_for_update()
        )
    )
    if len(accounts) != len(ids):
        raise ValueError("One or more transfer accounts do not exist")


def execute_payment(db: Session, payment: PaymentRequest, *, commit: bool = True) -> Transaction:
    existing = db.scalar(
        select(Transaction).where(
            Transaction.session_id == payment.session_id,
            Transaction.idempotency_key == payment.idempotency_key,
        )
    )
    if existing:
        payment.transaction_id = existing.txn_id
        payment.status = "COMPLETED"
        if commit:
            db.commit()
        else:
            db.flush()
        return existing

    if payment.status not in {"APPROVED", "PROCESSING"}:
        raise ValueError(f"Payment cannot execute from state {payment.status}")

    account = get_account(db, payment.session_id, payment.account_id)
    if account.balance < payment.amount:
        raise ValueError("Insufficient balance at execution time")
    if daily_transfer_total(db, payment.session_id, account.id) + payment.amount > account.daily_limit:
        raise ValueError("Daily transfer limit exceeded at execution time")

    bill: Bill | None = None
    target = find_beneficiary(db, payment.session_id, payment.beneficiary)
    category = target.kind if target else "payment"
    if payment.action == "pay_bill":
        bill = db.scalar(
            select(Bill).where(
                Bill.session_id == payment.session_id,
                Bill.provider == payment.beneficiary,
                Bill.status == "PENDING",
            )
        )
        if not bill:
            raise ValueError("Pending bill no longer exists")
        if bill.amount != payment.amount:
            raise ValueError("Payment amount does not match the authoritative pending bill")
        category = "bill_payment"

    payment.status = "PROCESSING"
    db.flush()
    account.balance -= payment.amount
    txn_id = f"PPA-{datetime.now(timezone.utc):%Y%m%d}-{uuid.uuid4().hex[:8].upper()}"
    txn = Transaction(
        session_id=payment.session_id,
        account_id=account.id,
        txn_id=txn_id,
        beneficiary_name=payment.beneficiary,
        amount=payment.amount,
        direction="DEBIT",
        category=category,
        status="COMPLETED",
        risk_score=payment.risk_score,
        idempotency_key=payment.idempotency_key,
    )
    db.add(txn)
    if bill:
        bill.status = "PAID"
    payment.transaction_id = txn_id
    payment.status = "COMPLETED"

    if commit:
        db.commit()
        db.refresh(txn)
    else:
        db.flush()
    return txn
