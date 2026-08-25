from sqlalchemy.orm import Session

from app.models import PaymentRequest
from app.services.payment_service import execute_payment


def execute_payment_tool(db: Session, payment: PaymentRequest, *, commit: bool = True) -> dict:
    txn = execute_payment(db, payment, commit=commit)
    return {
        "transaction_id": txn.txn_id,
        "status": txn.status,
        "amount": float(txn.amount),
        "beneficiary": txn.beneficiary_name,
    }
