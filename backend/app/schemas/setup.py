from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator


def _clean_nonblank(value: str) -> str:
    cleaned = " ".join(value.strip().split())
    if not cleaned:
        raise ValueError("Value cannot be blank")
    return cleaned


class AccountSetup(BaseModel):
    owner_name: str = Field(min_length=2, max_length=80)
    nickname: str = Field(default="Primary", min_length=2, max_length=60)
    account_type: Literal["savings", "current", "wallet"] = "savings"
    opening_balance: Decimal = Field(gt=0, le=Decimal("10000000"), max_digits=14, decimal_places=2)
    daily_limit: Decimal = Field(gt=0, le=Decimal("200000"), max_digits=14, decimal_places=2)

    @field_validator("owner_name", "nickname")
    @classmethod
    def clean_strings(cls, value: str) -> str:
        return _clean_nonblank(value)


class AccountUpdate(BaseModel):
    owner_name: str = Field(min_length=2, max_length=80)
    nickname: str = Field(min_length=2, max_length=60)
    account_type: Literal["savings", "current", "wallet"]
    daily_limit: Decimal = Field(gt=0, le=Decimal("200000"), max_digits=14, decimal_places=2)
    is_active: bool = True

    @field_validator("owner_name", "nickname")
    @classmethod
    def clean_strings(cls, value: str) -> str:
        return _clean_nonblank(value)


class AccountTransfer(BaseModel):
    source_account_id: int = Field(gt=0)
    destination_account_id: int = Field(gt=0)
    amount: Decimal = Field(gt=0, le=Decimal("200000"), max_digits=14, decimal_places=2)
    idempotency_key: str = Field(min_length=8, max_length=64)

    @field_validator("idempotency_key")
    @classmethod
    def clean_idempotency_key(cls, value: str) -> str:
        return _clean_nonblank(value)


class PaymentTargetCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    kind: str = Field(min_length=2, max_length=40)
    reference: str = Field(min_length=2, max_length=64)

    @field_validator("name", "kind", "reference")
    @classmethod
    def clean(cls, value: str) -> str:
        return _clean_nonblank(value)


class PaymentTargetUpdate(PaymentTargetCreate):
    pass


class BillCreate(BaseModel):
    provider: str = Field(min_length=2, max_length=100)
    amount: Decimal = Field(gt=0, le=Decimal("50000"), max_digits=14, decimal_places=2)
    due_date: str = Field(min_length=10, max_length=10)

    @field_validator("provider")
    @classmethod
    def clean_provider(cls, value: str) -> str:
        return _clean_nonblank(value)

    @field_validator("due_date")
    @classmethod
    def validate_due_date(cls, value: str) -> str:
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError as exc:
            raise ValueError("due_date must be a valid YYYY-MM-DD date") from exc


class BillUpdate(BillCreate):
    pass
