from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    Account,
    AgentEvent,
    AgentRun,
    Beneficiary,
    Bill,
    DemoSession,
    PaymentRequest,
    Transaction,
)


def _delete_session_children(db: Session, session_id: str) -> list[str]:
    run_ids = list(db.scalars(select(AgentRun.id).where(AgentRun.session_id == session_id)))
    if run_ids:
        db.execute(delete(AgentEvent).where(AgentEvent.run_id.in_(run_ids)))
    db.execute(delete(PaymentRequest).where(PaymentRequest.session_id == session_id))
    db.execute(delete(AgentRun).where(AgentRun.session_id == session_id))
    db.execute(delete(Transaction).where(Transaction.session_id == session_id))
    db.execute(delete(Bill).where(Bill.session_id == session_id))
    db.execute(delete(Beneficiary).where(Beneficiary.session_id == session_id))
    db.execute(delete(Account).where(Account.session_id == session_id))
    return run_ids


def _delete_demo_session_data(db: Session, session_id: str) -> list[str]:
    run_ids = _delete_session_children(db, session_id)
    db.execute(delete(DemoSession).where(DemoSession.id == session_id))
    return run_ids


def cleanup_expired_demo_sessions(db: Session) -> list[str]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.demo_session_ttl_hours)
    stale = list(db.scalars(select(DemoSession.id).where(DemoSession.updated_at < cutoff)))
    removed_runs: list[str] = []
    for session_id in stale:
        removed_runs.extend(_delete_demo_session_data(db, session_id))
    if stale:
        db.commit()
    return removed_runs


def ensure_demo_session(db: Session, session_id: str) -> list[str]:
    removed_runs = cleanup_expired_demo_sessions(db)
    session = db.get(DemoSession, session_id)
    if session:
        session.updated_at = datetime.now(timezone.utc)
        db.commit()
        return removed_runs

    now = datetime.now(timezone.utc)
    db.add(DemoSession(id=session_id, created_at=now, updated_at=now))
    db.commit()
    return removed_runs



def touch_demo_session(db: Session, session_id: str) -> tuple[bool, list[str]]:
    removed_runs = cleanup_expired_demo_sessions(db)
    session = db.get(DemoSession, session_id)
    if not session:
        return False, removed_runs
    session.updated_at = datetime.now(timezone.utc)
    db.commit()
    return True, removed_runs

def reset_demo_session(db: Session, session_id: str) -> list[str]:
    removed_runs = _delete_session_children(db, session_id)
    session = db.get(DemoSession, session_id)
    if session:
        session.updated_at = datetime.now(timezone.utc)
    db.commit()
    return removed_runs


def new_session_id() -> str:
    return str(uuid.uuid4())
