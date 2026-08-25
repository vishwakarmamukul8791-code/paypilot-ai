from pydantic import BaseModel


class DashboardOut(BaseModel):
    configured: bool
    owner_name: str | None = None
    masked_account: str | None = None
    balance: float = 0
    total_balance: float = 0
    currency: str = "INR"
    daily_limit: float = 0
    monthly_spending: float = 0
    transaction_count: int = 0
    risk_label: str = "AMOUNT-BASED"
    primary_account_id: int | None = None
    accounts: list[dict]
    beneficiaries: list[dict]
    bills: list[dict]
    recent_transactions: list[dict]
