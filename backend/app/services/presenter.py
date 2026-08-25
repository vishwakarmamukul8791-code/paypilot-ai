from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, AgentEvent, AgentRun, PaymentRequest


def run_detail(db: Session, run_id: str) -> dict:
    db.expire_all()
    run = db.get(AgentRun, run_id)
    if not run:
        raise KeyError(run_id)
    account = db.get(Account, run.account_id)
    source_account = account.nickname if account else "Archived account"
    payment = db.scalar(select(PaymentRequest).where(PaymentRequest.run_id == run_id))
    events = list(db.scalars(select(AgentEvent).where(AgentEvent.run_id == run_id).order_by(AgentEvent.ordinal)))
    return {
        "run_id": run.id,
        "account_id": run.account_id,
        "source_account": source_account,
        "status": run.status,
        "user_request": run.user_request,
        "intent": json.loads(run.intent_json or "{}"),
        "plan": json.loads(run.plan_json or "[]"),
        "summary": run.summary,
        "payment": None
        if not payment
        else {
            "account_id": payment.account_id,
            "source_account": source_account,
            "beneficiary": payment.beneficiary,
            "amount": float(payment.amount),
            "status": payment.status,
            "risk_score": payment.risk_score,
            "risk_level": payment.risk_level,
            "risk_reasons": json.loads(payment.risk_reasons_json or "[]"),
            "conditions": json.loads(payment.conditions_json or "{}"),
            "transaction_id": payment.transaction_id,
        },
        "events": [
            {
                "ordinal": e.ordinal,
                "kind": e.kind,
                "title": e.title,
                "detail": json.loads(e.detail_json or "{}"),
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ],
    }
