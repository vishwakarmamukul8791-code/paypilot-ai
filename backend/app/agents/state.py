from __future__ import annotations

from typing import TypedDict


class AgentState(TypedDict, total=False):
    run_id: str
    session_id: str
    account_id: int
    user_request: str
    intent: dict
    parser: str
    plan: list[str]
    context: dict
    risk: dict
    policy: dict
    route: str
    approval_status: str
    transaction: dict
    summary: str
