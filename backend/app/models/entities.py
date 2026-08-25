from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.db import Base

MONEY = Numeric(14, 2)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DemoSession(Base):
    __tablename__ = "demo_sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint("balance >= 0", name="ck_account_balance_nonnegative"),
        CheckConstraint("daily_limit > 0", name="ck_account_daily_limit_positive"),
        UniqueConstraint("session_id", "nickname", name="uq_account_session_nickname"),
        Index("uq_account_one_primary", "session_id", unique=True, sqlite_where=text("is_primary = 1"), postgresql_where=text("is_primary")),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("demo_sessions.id", ondelete="CASCADE"), index=True)
    owner_name: Mapped[str] = mapped_column(String(100))
    nickname: Mapped[str] = mapped_column(String(60), default="Primary")
    account_type: Mapped[str] = mapped_column(String(24), default="savings")
    masked_account: Mapped[str] = mapped_column(String(32))
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    balance: Mapped[Decimal] = mapped_column(MONEY)
    daily_limit: Mapped[Decimal] = mapped_column(MONEY)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Beneficiary(Base):
    __tablename__ = "beneficiaries"
    __table_args__ = (
        UniqueConstraint("session_id", "name", name="uq_beneficiary_session_name"),
        UniqueConstraint(
            "session_id",
            "kind",
            "account_mask",
            name="uq_beneficiary_session_kind_reference",
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("demo_sessions.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    verified: Mapped[bool] = mapped_column(Boolean, default=True)
    account_mask: Mapped[str] = mapped_column(String(64))


class Bill(Base):
    __tablename__ = "bills"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_bill_amount_positive"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("demo_sessions.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(100), index=True)
    amount: Mapped[Decimal] = mapped_column(MONEY)
    due_date: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24), default="PENDING")


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("session_id", "idempotency_key", name="uq_txn_session_idempotency"),
        CheckConstraint("amount > 0", name="ck_transaction_amount_positive"),
        CheckConstraint("risk_score >= 0 AND risk_score <= 100", name="ck_transaction_risk_score"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("demo_sessions.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"), index=True)
    txn_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    beneficiary_name: Mapped[str] = mapped_column(String(100))
    amount: Mapped[Decimal] = mapped_column(MONEY)
    direction: Mapped[str] = mapped_column(String(10), default="DEBIT")
    category: Mapped[str] = mapped_column(String(40), default="transfer")
    status: Mapped[str] = mapped_column(String(24), default="COMPLETED")
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    idempotency_key: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("demo_sessions.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"), index=True)
    user_request: Mapped[str] = mapped_column(Text)
    intent_json: Mapped[str] = mapped_column(Text, default="{}")
    plan_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(32), default="RUNNING")
    summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class PaymentRequest(Base):
    __tablename__ = "payment_requests"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payment_request_amount_positive"),
        CheckConstraint("risk_score >= 0 AND risk_score <= 100", name="ck_payment_request_risk_score"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("demo_sessions.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), unique=True, index=True)
    action: Mapped[str] = mapped_column(String(32))
    beneficiary: Mapped[str] = mapped_column(String(100))
    amount: Mapped[Decimal] = mapped_column(MONEY)
    conditions_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(32), default="DRAFT")
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    risk_level: Mapped[str] = mapped_column(String(16), default="LOW")
    risk_reasons_json: Mapped[str] = mapped_column(Text, default="[]")
    idempotency_key: Mapped[str] = mapped_column(String(80), unique=True)
    transaction_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AgentEvent(Base):
    __tablename__ = "agent_events"
    __table_args__ = (
        CheckConstraint("ordinal >= 0", name="ck_agent_event_ordinal_nonnegative"),
        UniqueConstraint("run_id", "ordinal", name="uq_agent_event_run_ordinal"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(120))
    detail_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
