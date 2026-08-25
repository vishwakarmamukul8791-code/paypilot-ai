from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PaymentConditions(BaseModel):
    minimum_remaining_balance: float | None = Field(default=None, ge=0)
    confirm_if_above: float | None = Field(default=None, ge=0)


class PaymentIntent(BaseModel):
    action: Literal["transfer", "pay_bill", "spend_summary", "unusual_transactions", "unknown"]
    beneficiary: str | None = None
    bill_provider: str | None = None
    amount: float | None = Field(default=None, gt=0)
    currency: str = "INR"
    conditions: PaymentConditions = Field(default_factory=PaymentConditions)
    confidence: float = Field(default=1.0, ge=0, le=1)
    guardrail_reason: str | None = None


class AgentRequest(BaseModel):
    message: str = Field(min_length=2, max_length=600)
    source_account_id: int | None = Field(default=None, gt=0)


class DecisionRequest(BaseModel):
    decision: Literal["approve", "reject"]


class AgentEventOut(BaseModel):
    ordinal: int
    kind: str
    title: str
    detail: dict
    created_at: str


class PaymentRequestOut(BaseModel):
    account_id: int
    source_account: str
    beneficiary: str
    amount: float
    status: str
    risk_score: int
    risk_level: str
    risk_reasons: list[str]
    conditions: dict
    transaction_id: str | None = None


class AgentRunOut(BaseModel):
    run_id: str
    account_id: int
    source_account: str
    status: str
    user_request: str
    intent: dict
    plan: list[str]
    summary: str
    payment: PaymentRequestOut | None = None
    events: list[AgentEventOut]
