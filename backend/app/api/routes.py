from __future__ import annotations

import re
import time
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agents import runtime
from app.core.config import settings
from app.database.db import get_db
from app.models import Account, AgentEvent, AgentRun, Beneficiary, Bill, PaymentRequest, Transaction
from app.schemas.agent import AgentRequest, AgentRunOut, DecisionRequest
from app.schemas.dashboard import DashboardOut
from app.schemas.setup import (
    AccountSetup,
    AccountUpdate,
    AccountTransfer,
    BillCreate,
    BillUpdate,
    PaymentTargetCreate,
    PaymentTargetUpdate,
)
from app.services.audit_service import log_event
from app.services.banking_service import get_account, list_accounts, monthly_spending
from app.services.payment_service import (
    begin_serialized_accounts_transaction,
    payment_execution_lock,
)
from app.services.presenter import run_detail
from app.services.rate_limit_service import global_agent_limiter, session_create_limiter
from app.services.session_service import ensure_demo_session, new_session_id, reset_demo_session, touch_demo_session

router = APIRouter(prefix="/api")
_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$")


def _session(db: Session, header: str | None) -> str:
    if not header:
        raise HTTPException(status_code=400, detail="X-Demo-Session header is required")
    sid = header.strip()
    if not _UUID_RE.fullmatch(sid):
        raise HTTPException(status_code=400, detail="Invalid simulation session identifier")
    exists, removed_runs = touch_demo_session(db, sid)
    runtime.delete_threads(removed_runs)
    if not exists:
        raise HTTPException(status_code=404, detail="Simulation session expired or does not exist. Create a new demo session.")
    return sid


def _account_or_409(db: Session, session_id: str, account_id: int | None = None, *, allow_paused: bool = False) -> Account:
    try:
        return get_account(db, session_id, account_id, require_active=not allow_paused)
    except ValueError as exc:
        detail = str(exc)
        if "paused" in detail.lower():
            raise HTTPException(status_code=409, detail=detail) from exc
        raise HTTPException(status_code=409, detail="Create the simulation account first. No financial data is preloaded.") from exc




def _normalize_target_kind(kind: str) -> str:
    return kind.strip().lower().replace(" ", "_")


def _duplicate_target_reference(
    db: Session,
    session_id: str,
    kind: str,
    reference: str,
    *,
    exclude_id: int | None = None,
) -> Beneficiary | None:
    query = select(Beneficiary).where(
        Beneficiary.session_id == session_id,
        func.lower(Beneficiary.kind) == kind.lower(),
        func.lower(Beneficiary.account_mask) == reference.strip().lower(),
    )
    if exclude_id is not None:
        query = query.where(Beneficiary.id != exclude_id)
    return db.scalar(query.limit(1))

def _enforce_agent_rate_limit(db: Session, session_id: str) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=1)
    recent = db.scalar(select(func.count(AgentRun.id)).where(AgentRun.session_id == session_id, AgentRun.created_at >= cutoff)) or 0
    if recent >= settings.agent_runs_per_minute:
        raise HTTPException(status_code=429, detail=f"Simulation rate limit reached. Try again shortly ({settings.agent_runs_per_minute} agent runs/minute).")
    if not global_agent_limiter.allow("agent-runs", settings.global_agent_runs_per_minute):
        raise HTTPException(status_code=429, detail="Public demo capacity limit reached. Try again shortly.")


def _account_dict(account: Account) -> dict:
    return {
        "id": account.id,
        "owner_name": account.owner_name,
        "nickname": account.nickname,
        "account_type": account.account_type,
        "masked_account": account.masked_account,
        "currency": account.currency,
        "balance": float(account.balance),
        "daily_limit": float(account.daily_limit),
        "is_primary": account.is_primary,
        "is_active": account.is_active,
    }


def _dashboard_payload(db: Session, sid: str) -> dict:
    accounts = list_accounts(db, sid)
    primary = next((a for a in accounts if a.is_primary), accounts[0] if accounts else None)
    account_by_id = {a.id: a for a in accounts}
    targets = list(db.scalars(select(Beneficiary).where(Beneficiary.session_id == sid).order_by(Beneficiary.name)))
    bills = list(db.scalars(select(Bill).where(Bill.session_id == sid).order_by(Bill.status.desc(), Bill.due_date, Bill.id)))
    txns = list(db.scalars(select(Transaction).where(Transaction.session_id == sid).order_by(desc(Transaction.created_at), desc(Transaction.id)).limit(30)))
    return {
        "configured": bool(accounts),
        "owner_name": primary.owner_name if primary else None,
        "masked_account": primary.masked_account if primary else None,
        "balance": float(primary.balance) if primary else 0,
        "total_balance": float(sum((a.balance for a in accounts), start=0)),
        "currency": primary.currency if primary else "INR",
        "daily_limit": float(primary.daily_limit) if primary else 0,
        "monthly_spending": float(monthly_spending(db, sid)) if accounts else 0,
        "transaction_count": db.query(Transaction).filter(Transaction.session_id == sid).count(),
        "risk_label": "AMOUNT-BASED",
        "primary_account_id": primary.id if primary else None,
        "accounts": [_account_dict(a) for a in accounts],
        "beneficiaries": [
            {"id": b.id, "name": b.name, "kind": b.kind, "verified": b.verified, "reference": b.account_mask}
            for b in targets
        ],
        "bills": [
            {"id": b.id, "provider": b.provider, "amount": float(b.amount), "due_date": b.due_date, "status": b.status}
            for b in bills
        ],
        "recent_transactions": [
            {
                "txn_id": t.txn_id,
                "account_id": t.account_id,
                "source_account": account_by_id[t.account_id].nickname if t.account_id in account_by_id else "Archived account",
                "name": t.beneficiary_name,
                "amount": float(t.amount),
                "direction": t.direction,
                "category": t.category,
                "status": t.status,
                "risk_score": t.risk_score,
                "created_at": t.created_at.isoformat(),
            }
            for t in txns[:10]
        ],
    }


@router.post("/demo/session")
def create_demo_session(db: Session = Depends(get_db)):
    if not session_create_limiter.allow("session-creates", settings.session_creates_per_minute):
        raise HTTPException(status_code=429, detail="Public demo session capacity limit reached. Try again shortly.")
    sid = new_session_id()
    removed_runs = ensure_demo_session(db, sid)
    runtime.delete_threads(removed_runs)
    return {"session_id": sid, "mode": "public-simulation", "message": "Empty isolated session created. No accounts, payees, bills, or transactions were preloaded."}


@router.post("/demo/reset")
def reset_demo(x_demo_session: str | None = Header(default=None, alias="X-Demo-Session"), db: Session = Depends(get_db)):
    sid = _session(db, x_demo_session)
    with payment_execution_lock(sid):
        removed_runs = reset_demo_session(db, sid)
    runtime.delete_threads(removed_runs)
    return {"ok": True, "session_id": sid, "message": "Session reset to a completely empty state."}


@router.post("/account", response_model=DashboardOut)
@router.post("/accounts", response_model=DashboardOut)
def create_account(payload: AccountSetup, x_demo_session: str | None = Header(default=None, alias="X-Demo-Session"), db: Session = Depends(get_db)):
    sid = _session(db, x_demo_session)
    with payment_execution_lock(sid):
        existing = list_accounts(db, sid)
        active_primary = next((a for a in existing if a.is_primary and a.is_active), None)
        make_primary = active_primary is None
        if make_primary:
            for item in existing:
                if item.is_primary:
                    item.is_primary = False
            db.flush()
        account = Account(
            session_id=sid,
            owner_name=payload.owner_name,
            nickname=payload.nickname,
            account_type=payload.account_type,
            masked_account=f"SIM-{uuid.uuid4().hex[-8:].upper()}",
            currency="INR",
            balance=payload.opening_balance,
            daily_limit=payload.daily_limit,
            is_primary=make_primary,
            is_active=True,
        )
        db.add(account)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(status_code=409, detail=f"An account named '{payload.nickname}' already exists in this session.") from exc
    return _dashboard_payload(db, sid)


@router.patch("/accounts/{account_id}", response_model=DashboardOut)
def update_account(account_id: int, payload: AccountUpdate, x_demo_session: str | None = Header(default=None, alias="X-Demo-Session"), db: Session = Depends(get_db)):
    sid = _session(db, x_demo_session)
    with payment_execution_lock(sid):
        account = _account_or_409(db, sid, account_id, allow_paused=True)
        if not payload.is_active:
            pending = db.scalar(select(PaymentRequest.id).where(PaymentRequest.session_id == sid, PaymentRequest.account_id == account.id, PaymentRequest.status == "AWAITING_APPROVAL").limit(1))
            if pending:
                raise HTTPException(status_code=409, detail="Resolve pending approvals before pausing this account.")
        account.owner_name = payload.owner_name
        account.nickname = payload.nickname
        account.account_type = payload.account_type
        account.daily_limit = payload.daily_limit
        account.is_active = payload.is_active
        if account.is_primary and not account.is_active:
            replacement = db.scalar(select(Account).where(Account.session_id == sid, Account.id != account.id, Account.is_active.is_(True)).order_by(Account.id))
            if replacement:
                account.is_primary = False
                db.flush()
                replacement.is_primary = True
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(status_code=409, detail=f"An account named '{payload.nickname}' already exists in this session.") from exc
    return _dashboard_payload(db, sid)


@router.post("/accounts/{account_id}/primary", response_model=DashboardOut)
def set_primary_account(account_id: int, x_demo_session: str | None = Header(default=None, alias="X-Demo-Session"), db: Session = Depends(get_db)):
    sid = _session(db, x_demo_session)
    with payment_execution_lock(sid):
        account = _account_or_409(db, sid, account_id)
        for item in list_accounts(db, sid):
            if item.id != account.id and item.is_primary:
                item.is_primary = False
        db.flush()
        account.is_primary = True
        db.commit()
    return _dashboard_payload(db, sid)


@router.post("/accounts/{account_id}/funds")
def add_simulated_funds_disabled(account_id: int, x_demo_session: str | None = Header(default=None, alias="X-Demo-Session"), db: Session = Depends(get_db)):
    sid = _session(db, x_demo_session)
    _account_or_409(db, sid, account_id, allow_paused=True)
    raise HTTPException(
        status_code=410,
        detail="Direct balance top-ups are disabled after account creation. Use an internal account transfer so every credit has a matching source debit.",
    )


@router.post("/accounts/transfer", response_model=DashboardOut)
def transfer_between_accounts(
    payload: AccountTransfer,
    x_demo_session: str | None = Header(default=None, alias="X-Demo-Session"),
    db: Session = Depends(get_db),
):
    sid = _session(db, x_demo_session)
    if payload.source_account_id == payload.destination_account_id:
        raise HTTPException(status_code=422, detail="Source and destination accounts must be different.")

    debit_key = f"internal-{payload.idempotency_key}-debit"
    credit_key = f"internal-{payload.idempotency_key}-credit"

    with payment_execution_lock(sid):
        try:
            begin_serialized_accounts_transaction(
                db,
                sid,
                [payload.source_account_id, payload.destination_account_id],
            )
        except ValueError as exc:
            db.rollback()
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        existing_debit = db.scalar(
            select(Transaction).where(
                Transaction.session_id == sid,
                Transaction.idempotency_key == debit_key,
            )
        )
        existing_credit = db.scalar(
            select(Transaction).where(
                Transaction.session_id == sid,
                Transaction.idempotency_key == credit_key,
            )
        )
        if existing_debit and existing_credit:
            db.rollback()
            return _dashboard_payload(db, sid)
        if existing_debit or existing_credit:
            db.rollback()
            raise HTTPException(status_code=409, detail="Internal transfer ledger is incomplete; no retry was executed.")

        source = _account_or_409(db, sid, payload.source_account_id)
        destination = _account_or_409(db, sid, payload.destination_account_id)

        if source.balance < payload.amount:
            db.rollback()
            raise HTTPException(status_code=409, detail=f"Insufficient balance in {source.nickname}.")
        if destination.balance + payload.amount > 10000000:
            db.rollback()
            raise HTTPException(status_code=422, detail="Destination simulation balance cannot exceed ₹1,00,00,000.")

        source.balance -= payload.amount
        destination.balance += payload.amount
        transfer_ref = f"PPT-{datetime.now(timezone.utc):%Y%m%d}-{uuid.uuid4().hex[:8].upper()}"
        created_at = datetime.now(timezone.utc)

        debit = Transaction(
            session_id=sid,
            account_id=source.id,
            txn_id=f"{transfer_ref}-D",
            beneficiary_name=f"Transfer to {destination.nickname}",
            amount=payload.amount,
            direction="DEBIT",
            category="internal_transfer",
            status="COMPLETED",
            risk_score=0,
            idempotency_key=debit_key,
            created_at=created_at,
        )
        credit = Transaction(
            session_id=sid,
            account_id=destination.id,
            txn_id=f"{transfer_ref}-C",
            beneficiary_name=f"Transfer from {source.nickname}",
            amount=payload.amount,
            direction="CREDIT",
            category="internal_transfer",
            status="COMPLETED",
            risk_score=0,
            idempotency_key=credit_key,
            created_at=created_at,
        )
        db.add_all([debit, credit])
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise

    return _dashboard_payload(db, sid)


@router.post("/targets")
def create_payment_target(payload: PaymentTargetCreate, x_demo_session: str | None = Header(default=None, alias="X-Demo-Session"), db: Session = Depends(get_db)):
    sid = _session(db, x_demo_session)
    _account_or_409(db, sid)
    kind = _normalize_target_kind(payload.kind)
    duplicate_reference = _duplicate_target_reference(db, sid, kind, payload.reference)
    if duplicate_reference:
        raise HTTPException(
            status_code=409,
            detail=f"This {kind.replace('_', ' ')} reference is already saved for '{duplicate_reference.name}'.",
        )
    target = Beneficiary(session_id=sid, name=payload.name, kind=kind, verified=True, account_mask=payload.reference)
    db.add(target)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"A payment destination named '{payload.name}' already exists.") from exc
    return {"id": target.id, "name": target.name, "kind": target.kind, "reference": target.account_mask, "confirmed": True}


@router.patch("/targets/{target_id}")
def update_payment_target(target_id: int, payload: PaymentTargetUpdate, x_demo_session: str | None = Header(default=None, alias="X-Demo-Session"), db: Session = Depends(get_db)):
    sid = _session(db, x_demo_session)
    target = db.scalar(select(Beneficiary).where(Beneficiary.id == target_id, Beneficiary.session_id == sid))
    if not target:
        raise HTTPException(status_code=404, detail="Payment destination not found")
    old_name = target.name
    pending_payment = db.scalar(select(PaymentRequest.id).where(PaymentRequest.session_id == sid, PaymentRequest.beneficiary == old_name, PaymentRequest.status == "AWAITING_APPROVAL").limit(1))
    if pending_payment:
        raise HTTPException(status_code=409, detail="Resolve pending approvals before editing this destination.")
    kind = _normalize_target_kind(payload.kind)
    duplicate_reference = _duplicate_target_reference(
        db, sid, kind, payload.reference, exclude_id=target.id
    )
    if duplicate_reference:
        raise HTTPException(
            status_code=409,
            detail=f"This {kind.replace('_', ' ')} reference is already saved for '{duplicate_reference.name}'.",
        )
    target.name = payload.name
    target.kind = kind
    target.account_mask = payload.reference
    for bill in db.scalars(select(Bill).where(Bill.session_id == sid, Bill.provider == old_name, Bill.status == "PENDING")):
        bill.provider = payload.name
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"A payment destination named '{payload.name}' already exists.") from exc
    return {"id": target.id, "name": target.name, "kind": target.kind, "reference": target.account_mask, "confirmed": True}


@router.delete("/targets/{target_name}")
def delete_payment_target(target_name: str, x_demo_session: str | None = Header(default=None, alias="X-Demo-Session"), db: Session = Depends(get_db)):
    sid = _session(db, x_demo_session)
    target = db.scalar(select(Beneficiary).where(Beneficiary.session_id == sid, func.lower(Beneficiary.name) == target_name.strip().lower()))
    if not target:
        raise HTTPException(status_code=404, detail="Payment destination not found")
    pending_bill = db.scalar(select(Bill).where(Bill.session_id == sid, func.lower(Bill.provider) == target.name.lower(), Bill.status == "PENDING"))
    if pending_bill:
        raise HTTPException(status_code=409, detail="Pay or remove the pending bill before removing this biller destination.")
    db.delete(target)
    db.commit()
    return {"ok": True}


@router.post("/bills")
def create_bill(payload: BillCreate, x_demo_session: str | None = Header(default=None, alias="X-Demo-Session"), db: Session = Depends(get_db)):
    sid = _session(db, x_demo_session)
    _account_or_409(db, sid)
    existing = db.scalar(select(Bill).where(Bill.session_id == sid, func.lower(Bill.provider) == payload.provider.lower(), Bill.status == "PENDING"))
    if existing:
        raise HTTPException(status_code=409, detail=f"A pending bill for '{payload.provider}' already exists.")
    target = db.scalar(select(Beneficiary).where(Beneficiary.session_id == sid, func.lower(Beneficiary.name) == payload.provider.lower()))
    if not target:
        db.add(Beneficiary(session_id=sid, name=payload.provider, kind="bill_payment", verified=True, account_mask=f"BILL:{payload.provider}"[:64]))
        db.flush()
    bill = Bill(session_id=sid, provider=payload.provider, amount=payload.amount, due_date=payload.due_date, status="PENDING")
    db.add(bill)
    db.commit()
    return {"id": bill.id, "provider": bill.provider, "amount": float(bill.amount), "due_date": bill.due_date, "status": bill.status}


@router.patch("/bills/{bill_id}")
def update_bill(bill_id: int, payload: BillUpdate, x_demo_session: str | None = Header(default=None, alias="X-Demo-Session"), db: Session = Depends(get_db)):
    sid = _session(db, x_demo_session)
    bill = db.scalar(select(Bill).where(Bill.id == bill_id, Bill.session_id == sid))
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    if bill.status != "PENDING":
        raise HTTPException(status_code=409, detail="Paid bills are immutable ledger history.")
    pending_payment = db.scalar(select(PaymentRequest.id).where(PaymentRequest.session_id == sid, PaymentRequest.beneficiary == bill.provider, PaymentRequest.status == "AWAITING_APPROVAL").limit(1))
    if pending_payment:
        raise HTTPException(status_code=409, detail="Resolve pending approval before editing this bill.")
    old_provider = bill.provider
    bill.provider = payload.provider
    bill.amount = payload.amount
    bill.due_date = payload.due_date
    target = db.scalar(select(Beneficiary).where(Beneficiary.session_id == sid, func.lower(Beneficiary.name) == old_provider.lower()))
    if target and target.kind == "bill_payment":
        existing_target = db.scalar(select(Beneficiary).where(Beneficiary.session_id == sid, func.lower(Beneficiary.name) == payload.provider.lower(), Beneficiary.id != target.id))
        if existing_target:
            db.delete(target)
        else:
            target.name = payload.provider
            target.account_mask = f"BILL:{payload.provider}"[:64]
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Bill provider conflicts with an existing payment destination.") from exc
    return {"id": bill.id, "provider": bill.provider, "amount": float(bill.amount), "due_date": bill.due_date, "status": bill.status}


@router.delete("/bills/{bill_id}")
def delete_bill(bill_id: int, x_demo_session: str | None = Header(default=None, alias="X-Demo-Session"), db: Session = Depends(get_db)):
    sid = _session(db, x_demo_session)
    bill = db.scalar(select(Bill).where(Bill.id == bill_id, Bill.session_id == sid))
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    if bill.status != "PENDING":
        raise HTTPException(status_code=409, detail="Paid bills are immutable ledger history.")
    pending_payment = db.scalar(select(PaymentRequest.id).where(PaymentRequest.session_id == sid, PaymentRequest.beneficiary == bill.provider, PaymentRequest.status == "AWAITING_APPROVAL").limit(1))
    if pending_payment:
        raise HTTPException(status_code=409, detail="Resolve pending approval before removing this bill.")
    provider = bill.provider
    db.delete(bill)
    db.flush()
    target = db.scalar(select(Beneficiary).where(Beneficiary.session_id == sid, func.lower(Beneficiary.name) == provider.lower(), Beneficiary.kind == "bill_payment"))
    if target:
        other_bill = db.scalar(select(Bill.id).where(Bill.session_id == sid, func.lower(Bill.provider) == provider.lower(), Bill.status == "PENDING").limit(1))
        if not other_bill:
            db.delete(target)
    db.commit()
    return {"ok": True}


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(x_demo_session: str | None = Header(default=None, alias="X-Demo-Session"), db: Session = Depends(get_db)):
    sid = _session(db, x_demo_session)
    return _dashboard_payload(db, sid)


@router.get("/transactions")
def transactions(x_demo_session: str | None = Header(default=None, alias="X-Demo-Session"), db: Session = Depends(get_db)):
    sid = _session(db, x_demo_session)
    accounts = {a.id: a for a in list_accounts(db, sid)}
    txns = list(db.scalars(select(Transaction).where(Transaction.session_id == sid).order_by(desc(Transaction.created_at), desc(Transaction.id)).limit(200)))
    return [
        {
            "txn_id": t.txn_id,
            "account_id": t.account_id,
            "source_account": accounts[t.account_id].nickname if t.account_id in accounts else "Archived account",
            "name": t.beneficiary_name,
            "amount": float(t.amount),
            "direction": t.direction,
            "category": t.category,
            "status": t.status,
            "risk_score": t.risk_score,
            "created_at": t.created_at.isoformat(),
        }
        for t in txns
    ]


@router.post("/agent/run", response_model=AgentRunOut)
def start_agent(payload: AgentRequest, x_demo_session: str | None = Header(default=None, alias="X-Demo-Session"), db: Session = Depends(get_db)):
    sid = _session(db, x_demo_session)
    with payment_execution_lock(sid):
        account = _account_or_409(db, sid, payload.source_account_id)
        _enforce_agent_rate_limit(db, sid)
        run_id = str(uuid.uuid4())
        db.add(AgentRun(id=run_id, session_id=sid, account_id=account.id, user_request=payload.message, status="RUNNING"))
        db.commit()
        started = time.perf_counter()
        try:
            runtime.start({"run_id": run_id, "session_id": sid, "account_id": account.id, "user_request": payload.message})
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            log_event(db, run_id, "METRIC", "Agent run latency", {"duration_ms": elapsed_ms, "runtime": runtime.mode, "account_id": account.id})
        except Exception as exc:
            db.rollback(); db.expire_all()
            run = db.get(AgentRun, run_id)
            if run:
                run.status = "FAILED"; run.summary = "Agent run failed safely; no payment was executed."; db.commit()
                log_event(db, run_id, "ERROR", "Agent orchestration failed safely", {"error_type": type(exc).__name__})
            raise HTTPException(status_code=500, detail="Agent execution failed safely. No payment was executed.") from exc
        return run_detail(db, run_id)


@router.post("/agent/runs/{run_id}/decision", response_model=AgentRunOut)
def decide(run_id: str, payload: DecisionRequest, x_demo_session: str | None = Header(default=None, alias="X-Demo-Session"), db: Session = Depends(get_db)):
    sid = _session(db, x_demo_session)
    with payment_execution_lock(sid):
        db.expire_all()
        run = db.get(AgentRun, run_id)
        if not run or run.session_id != sid:
            raise HTTPException(status_code=404, detail="Agent run not found")
        if run.status != "AWAITING_APPROVAL":
            had_human_approval = db.scalar(select(AgentEvent.id).where(AgentEvent.run_id == run_id, AgentEvent.kind == "APPROVAL", AgentEvent.title == "Human approval required").limit(1)) is not None
            if had_human_approval and payload.decision == "approve" and run.status in {"COMPLETED", "BLOCKED", "FAILED"}:
                return run_detail(db, run_id)
            if had_human_approval and payload.decision == "reject" and run.status == "REJECTED":
                return run_detail(db, run_id)
            raise HTTPException(status_code=409, detail=f"Run is not awaiting approval; current state is {run.status}")
        started = time.perf_counter()
        try:
            runtime.resume(run_id, sid, payload.decision)
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            log_event(db, run_id, "METRIC", "Approval decision latency", {"duration_ms": elapsed_ms, "decision": payload.decision})
        except Exception as exc:
            db.rollback(); db.expire_all()
            current = db.get(AgentRun, run_id)
            if current and current.session_id == sid and current.status in {"COMPLETED", "BLOCKED", "REJECTED", "FAILED"}:
                return run_detail(db, run_id)
            raise HTTPException(status_code=500, detail="Decision processing failed safely. No duplicate payment was created.") from exc
        return run_detail(db, run_id)


@router.get("/agent/runs/{run_id}", response_model=AgentRunOut)
def get_run(run_id: str, x_demo_session: str | None = Header(default=None, alias="X-Demo-Session"), db: Session = Depends(get_db)):
    sid = _session(db, x_demo_session)
    run = db.get(AgentRun, run_id)
    if not run or run.session_id != sid:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return run_detail(db, run_id)


@router.get("/agent/runs")
def list_runs(x_demo_session: str | None = Header(default=None, alias="X-Demo-Session"), db: Session = Depends(get_db)):
    sid = _session(db, x_demo_session)
    accounts = {a.id: a for a in list_accounts(db, sid)}
    runs = list(db.scalars(select(AgentRun).where(AgentRun.session_id == sid).order_by(desc(AgentRun.created_at)).limit(50)))
    return [
        {
            "run_id": r.id,
            "account_id": r.account_id,
            "source_account": accounts[r.account_id].nickname if r.account_id in accounts else "Archived account",
            "status": r.status,
            "user_request": r.user_request,
            "summary": r.summary,
            "created_at": r.created_at.isoformat(),
        }
        for r in runs
    ]
