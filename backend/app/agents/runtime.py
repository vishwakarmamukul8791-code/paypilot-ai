from __future__ import annotations

import atexit
import json
import os
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from app.agents.state import AgentState
from app.core.config import settings
from app.database.db import SessionLocal
from app.models import AgentRun, PaymentRequest
from app.schemas.agent import PaymentConditions, PaymentIntent
from app.services.audit_service import log_event
from app.services.banking_service import find_beneficiary, get_account, monthly_debit_history
from app.services.intent_service import parse_intent
from app.services.payment_service import (
    begin_serialized_payment_transaction,
    payment_execution_lock,
)
from app.tools.banking_tools import (
    find_beneficiary_tool,
    get_balance_tool,
    get_bill_tool,
    monthly_spending_tool,
)
from app.tools.payment_tools import execute_payment_tool
from app.tools.safety_tools import calculate_risk_tool, policy_check_tool


def _json(obj: Any) -> str:
    return json.dumps(obj, default=str)


def _log_tool(
    db,
    run_id: str,
    name: str,
    args: dict,
    result: dict,
    *,
    commit: bool = True,
) -> None:
    log_event(db, run_id, "TOOL_CALL", name, {"args": args}, commit=commit)
    log_event(db, run_id, "TOOL_RESULT", f"{name} result", result, commit=commit)


def parse_node(state: AgentState) -> dict:
    intent, parser = parse_intent(state["user_request"])
    with SessionLocal() as db:
        run = db.get(AgentRun, state["run_id"])
        if not run:
            raise ValueError("Agent run no longer exists")
        run.intent_json = intent.model_dump_json()
        db.commit()
        log_event(
            db,
            state["run_id"],
            "INTENT",
            "Payment intent parsed",
            {"parser": parser, **intent.model_dump()},
        )
    return {"intent": intent.model_dump(), "parser": parser}


def plan_node(state: AgentState) -> dict:
    intent = PaymentIntent.model_validate(state["intent"])
    if intent.action == "transfer":
        plan = [
            "Resolve user-created payment destination",
            "Read simulation balance",
            "Assign fixed amount-based risk band",
            "Evaluate deterministic payment policies",
            "Auto-execute up to ₹2,000 or request approval above ₹2,000",
            "Revalidate latest state",
            "Execute and verify payment",
        ]
    elif intent.action == "pay_bill":
        plan = [
            "Fetch user-created pending bill",
            "Read simulation balance",
            "Assign fixed amount-based risk band",
            "Evaluate deterministic payment policies",
            "Auto-execute up to ₹2,000 or request approval above ₹2,000",
            "Revalidate bill and policy",
            "Execute bill payment",
        ]
    elif intent.action == "spend_summary":
        plan = [
            "Read transaction ledger",
            "Calculate current-month debits",
            "Return grounded spending summary",
        ]
    elif intent.action == "unusual_transactions":
        plan = [
            "Read current-month debit history",
            "Apply fixed amount-based risk bands",
            "Surface medium/high-risk payments",
        ]
    else:
        plan = ["Stop safely", "Explain why the instruction is unsupported"]

    with SessionLocal() as db:
        run = db.get(AgentRun, state["run_id"])
        if not run:
            raise ValueError("Agent run no longer exists")
        run.plan_json = _json(plan)
        db.commit()
        log_event(db, state["run_id"], "PLAN", "Agent plan created", {"steps": plan})
    return {"plan": plan}


def route_after_plan(state: AgentState) -> str:
    action = state["intent"].get("action")
    if action in {"spend_summary", "unusual_transactions"}:
        return "analysis"
    if action in {"transfer", "pay_bill"}:
        return "payment"
    return "unknown"


def analysis_node(state: AgentState) -> dict:
    action = state["intent"]["action"]
    with SessionLocal() as db:
        if action == "spend_summary":
            result = monthly_spending_tool(db, state["session_id"], state.get("account_id"))
            _log_tool(db, state["run_id"], "monthly_spending", {}, result)
            summary = f"You spent ₹{result['monthly_spending']:,.2f} this month in this simulation session."
        else:
            txns = monthly_debit_history(db, state["session_id"], state.get("account_id"))
            unusual = [t for t in txns if t.risk_score >= 60]
            result = {
                "count": len(unusual),
                "transactions": [
                    {
                        "destination": t.beneficiary_name,
                        "amount": float(t.amount),
                        "risk_score": t.risk_score,
                    }
                    for t in unusual[:5]
                ],
            }
            _log_tool(db, state["run_id"], "analyze_current_month_transactions", {}, result)
            if unusual:
                top = max(unusual, key=lambda t: (t.risk_score, t.amount))
                summary = (
                    f"I found {len(unusual)} medium/high-risk payment(s) this month. "
                    f"Highest amount signal: {top.beneficiary_name}, ₹{top.amount:,.2f}, "
                    f"risk {top.risk_score}/100."
                )
            else:
                summary = (
                    "No medium/high-risk payments were found this month under the "
                    "fixed amount-based risk bands."
                )

        run = db.get(AgentRun, state["run_id"])
        if not run:
            raise ValueError("Agent run no longer exists")
        run.status = "COMPLETED"
        run.summary = summary
        db.commit()
        log_event(db, state["run_id"], "FINAL", "Analysis completed", {"summary": summary})
    return {"summary": summary, "route": "done"}


def unknown_node(state: AgentState) -> dict:
    intent = PaymentIntent.model_validate(state["intent"])
    summary = intent.guardrail_reason or (
        "I could not safely map that request to a supported action. Create a payment "
        "destination first, then try one immediate payment/recharge, one bill payment, "
        "a spending summary, or an unusual-transaction check."
    )
    with SessionLocal() as db:
        run = db.get(AgentRun, state["run_id"])
        if not run:
            raise ValueError("Agent run no longer exists")
        run.status = "BLOCKED"
        run.summary = summary
        db.commit()
        log_event(
            db,
            state["run_id"],
            "GUARDRAIL",
            "Unsupported request blocked",
            {"reason": intent.guardrail_reason or "unknown_intent"},
        )
    return {"summary": summary, "route": "blocked"}


def payment_context_node(state: AgentState) -> dict:
    intent = PaymentIntent.model_validate(state["intent"])
    context: dict = {}
    with SessionLocal() as db:
        balance = get_balance_tool(db, state["session_id"], state.get("account_id"))
        _log_tool(db, state["run_id"], "get_balance", {}, balance)
        context["account"] = balance

        if intent.action == "pay_bill":
            bill = get_bill_tool(db, state["session_id"], intent.bill_provider)
            _log_tool(
                db,
                state["run_id"],
                "get_bill",
                {"provider": intent.bill_provider},
                bill,
            )
            context["bill"] = bill
            context["requested_amount"] = intent.amount
            if bill["found"]:
                context["beneficiary"] = {
                    "found": True,
                    "name": bill["provider"],
                    "verified": True,
                }
                context["amount"] = bill["amount"]
        else:
            beneficiary = find_beneficiary_tool(db, state["session_id"], intent.beneficiary)
            _log_tool(
                db,
                state["run_id"],
                "find_payment_destination",
                {"name": intent.beneficiary},
                beneficiary,
            )
            context["beneficiary"] = beneficiary
            context["amount"] = intent.amount
    return {"context": context}


def _block_run(db, state: AgentState, summary: str, title: str, detail: dict) -> dict:
    run = db.get(AgentRun, state["run_id"])
    if not run:
        raise ValueError("Agent run no longer exists")
    run.status = "BLOCKED"
    run.summary = summary
    db.commit()
    log_event(db, state["run_id"], "GUARDRAIL", title, detail)
    return {"route": "blocked", "summary": summary}


def _requires_human_approval(amount: Decimal, conditions: PaymentConditions) -> bool:
    if amount > settings.auto_execute_threshold:
        return True
    if conditions.confirm_if_above is not None and amount > Decimal(str(conditions.confirm_if_above)):
        return True
    return False


def evaluate_node(state: AgentState) -> dict:
    intent = PaymentIntent.model_validate(state["intent"])
    context = state.get("context", {})
    amount = context.get("amount")
    beneficiary_info = context.get("beneficiary") or {}

    with SessionLocal() as db:
        if intent.action == "pay_bill":
            bill = context.get("bill") or {}
            requested_amount = context.get("requested_amount")
            if not bill.get("found"):
                return _block_run(
                    db,
                    state,
                    "Bill payment blocked because the requested pending bill could not be resolved unambiguously.",
                    "Pending bill not found",
                    {"provider": intent.bill_provider},
                )
            if requested_amount is not None and abs(float(requested_amount) - float(bill["amount"])) > 0.005:
                return _block_run(
                    db,
                    state,
                    (
                        f"Bill payment blocked because requested ₹{requested_amount:,.2f} does not match "
                        f"the pending {bill['provider']} bill of ₹{bill['amount']:,.2f}."
                    ),
                    "Bill amount mismatch",
                    {
                        "requested_amount": requested_amount,
                        "bill_amount": bill["amount"],
                        "provider": bill["provider"],
                    },
                )

        beneficiary = find_beneficiary(db, state["session_id"], beneficiary_info.get("name"))
        if amount is None:
            return _block_run(
                db,
                state,
                "Payment blocked because the amount is missing or ambiguous.",
                "Missing amount",
                {},
            )
        if not beneficiary:
            return _block_run(
                db,
                state,
                (
                    "Payment blocked because destination "
                    f"'{beneficiary_info.get('name') or 'unknown'}' has not been created in this session."
                ),
                "Unknown payment destination",
                {"destination": beneficiary_info.get("name")},
            )

        amount_d = Decimal(str(amount))
        risk = calculate_risk_tool(db, state["session_id"], float(amount_d), beneficiary)
        _log_tool(
            db,
            state["run_id"],
            "calculate_risk",
            {"amount": float(amount_d), "destination": beneficiary.name},
            risk,
        )
        policy = policy_check_tool(
            db,
            state["session_id"],
            float(amount_d),
            beneficiary,
            intent.conditions,
            risk,
            state.get("account_id"),
        )
        _log_tool(
            db,
            state["run_id"],
            "check_payment_policy",
            {"conditions": intent.conditions.model_dump()},
            policy,
        )

        needs_approval = _requires_human_approval(amount_d, intent.conditions)
        status = (
            "AWAITING_APPROVAL"
            if needs_approval and policy["passed"]
            else "APPROVED"
            if policy["passed"]
            else "BLOCKED"
        )
        payment = db.scalar(select(PaymentRequest).where(PaymentRequest.run_id == state["run_id"]))
        if not payment:
            payment = PaymentRequest(
                session_id=state["session_id"],
                account_id=int(state["account_id"]),
                run_id=state["run_id"],
                action=intent.action,
                beneficiary=beneficiary.name,
                amount=amount_d,
                conditions_json=intent.conditions.model_dump_json(),
                status=status,
                risk_score=risk["score"],
                risk_level=risk["level"],
                risk_reasons_json=_json(risk["reasons"]),
                idempotency_key=f"pay-{state['run_id']}",
            )
            db.add(payment)
        else:
            payment.status = status
            payment.risk_score = risk["score"]
            payment.risk_level = risk["level"]
            payment.risk_reasons_json = _json(risk["reasons"])

        run = db.get(AgentRun, state["run_id"])
        if not run:
            raise ValueError("Agent run no longer exists")

        if policy["passed"] and needs_approval:
            run.status = "AWAITING_APPROVAL"
            run.summary = (
                f"₹{float(amount_d):,.2f} payment to {beneficiary.name} passed safety checks "
                "and is waiting for your approval."
            )
            route = "approval"
            log_event(
                db,
                state["run_id"],
                "APPROVAL",
                "Human approval required",
                {
                    "amount": float(amount_d),
                    "destination": beneficiary.name,
                    "threshold": float(settings.auto_execute_threshold),
                },
            )
        elif policy["passed"]:
            run.status = "PROCESSING"
            run.summary = (
                f"₹{float(amount_d):,.2f} is within the ₹{settings.auto_execute_threshold:,.0f} "
                "auto-execution threshold; safety checks passed."
            )
            route = "auto_execute"
            log_event(
                db,
                state["run_id"],
                "AUTO_AUTHORIZATION",
                "Human approval not required",
                {
                    "amount": float(amount_d),
                    "threshold": float(settings.auto_execute_threshold),
                    "risk_level": risk["level"],
                },
            )
        else:
            failed = [c for c in policy["checks"] if not c["passed"]]
            run.status = "BLOCKED"
            run.summary = "Payment blocked: " + "; ".join(c["detail"] for c in failed)
            route = "blocked"
            log_event(
                db,
                state["run_id"],
                "POLICY",
                "Payment blocked by deterministic policy",
                {"failed_checks": failed},
            )

        db.commit()
        return {"risk": risk, "policy": policy, "route": route, "summary": run.summary}


def route_after_evaluate(state: AgentState) -> str:
    return state.get("route") if state.get("route") in {"approval", "auto_execute"} else "end"


def _terminal_payment_result(db, payment: PaymentRequest, run: AgentRun) -> dict | None:
    if payment.status == "COMPLETED":
        return {
            "approval_status": "completed",
            "summary": run.summary,
            "route": "done",
        }
    if payment.status in {"BLOCKED", "REJECTED", "FAILED"}:
        return {
            "approval_status": payment.status.lower(),
            "summary": run.summary,
            "route": "blocked" if payment.status == "BLOCKED" else "done",
        }
    return None


def _execute_authorized(state: AgentState, authorization: str) -> dict:
    with payment_execution_lock(state["session_id"]):
        with SessionLocal() as db:
            try:
                payment = db.scalar(
                    select(PaymentRequest).where(PaymentRequest.run_id == state["run_id"])
                )
                if not payment:
                    raise ValueError("No payment request found")
                begin_serialized_payment_transaction(db, state["session_id"], payment.account_id)
                db.expire_all()
                payment = db.scalar(
                    select(PaymentRequest).where(PaymentRequest.run_id == state["run_id"])
                )
                run = db.get(AgentRun, state["run_id"])
                if not payment or not run:
                    raise ValueError("No payment request found")

                terminal = _terminal_payment_result(db, payment, run)
                if terminal:
                    db.rollback()
                    return terminal

                expected = "AWAITING_APPROVAL" if authorization == "human" else "APPROVED"
                if payment.status != expected:
                    raise ValueError(
                        f"Payment authorization state mismatch; current state is {payment.status}"
                    )

                beneficiary = find_beneficiary(db, state["session_id"], payment.beneficiary)
                if not beneficiary:
                    payment.status = "BLOCKED"
                    run.status = "BLOCKED"
                    run.summary = (
                        "Execution stopped because the payment destination no longer exists in this session. "
                        "No ledger change was made."
                    )
                    log_event(
                        db,
                        state["run_id"],
                        "POLICY_REVALIDATION",
                        "Payment destination changed before execution",
                        {"destination": payment.beneficiary},
                        commit=False,
                    )
                    db.commit()
                    return {
                        "approval_status": "blocked",
                        "summary": run.summary,
                        "route": "blocked",
                    }

                conditions = PaymentConditions.model_validate_json(payment.conditions_json or "{}")
                if payment.action == "pay_bill":
                    bill = get_bill_tool(db, state["session_id"], payment.beneficiary)
                    if not bill["found"] or Decimal(payment.amount) != Decimal(str(bill["amount"])):
                        payment.status = "BLOCKED"
                        run.status = "BLOCKED"
                        run.summary = (
                            "Execution stopped because the pending bill changed or is no longer available. "
                            "No ledger change was made."
                        )
                        log_event(
                            db,
                            state["run_id"],
                            "POLICY_REVALIDATION",
                            "Bill changed before execution",
                            bill,
                            commit=False,
                        )
                        db.commit()
                        return {
                            "approval_status": "blocked",
                            "summary": run.summary,
                            "route": "blocked",
                        }

                risk = calculate_risk_tool(
                    db,
                    state["session_id"],
                    float(payment.amount),
                    beneficiary,
                )
                policy = policy_check_tool(
                    db,
                    state["session_id"],
                    float(payment.amount),
                    beneficiary,
                    conditions,
                    risk,
                    payment.account_id,
                )
                _log_tool(
                    db,
                    state["run_id"],
                    "revalidate_payment_policy",
                    {
                        "amount": float(payment.amount),
                        "destination": payment.beneficiary,
                        "conditions": conditions.model_dump(),
                    },
                    policy,
                    commit=False,
                )

                if not policy["passed"]:
                    failed = [c for c in policy["checks"] if not c["passed"]]
                    payment.status = "BLOCKED"
                    payment.risk_score = risk["score"]
                    payment.risk_level = risk["level"]
                    payment.risk_reasons_json = _json(risk["reasons"])
                    run.status = "BLOCKED"
                    run.summary = "Execution stopped by latest-state revalidation: " + "; ".join(
                        c["detail"] for c in failed
                    )
                    log_event(
                        db,
                        state["run_id"],
                        "POLICY_REVALIDATION",
                        "Payment blocked after state changed",
                        {"failed_checks": failed},
                        commit=False,
                    )
                    db.commit()
                    return {
                        "approval_status": "blocked",
                        "summary": run.summary,
                        "route": "blocked",
                    }

                if authorization == "auto" and _requires_human_approval(
                    Decimal(payment.amount), conditions
                ):
                    payment.status = "AWAITING_APPROVAL"
                    run.status = "AWAITING_APPROVAL"
                    run.summary = (
                        "Payment now requires human approval after final authorization revalidation."
                    )
                    log_event(
                        db,
                        state["run_id"],
                        "APPROVAL",
                        "Approval required after revalidation",
                        {},
                        commit=False,
                    )
                    db.commit()
                    return {
                        "approval_status": "required",
                        "summary": run.summary,
                        "route": "approval",
                    }

                payment.risk_score = risk["score"]
                payment.risk_level = risk["level"]
                payment.risk_reasons_json = _json(risk["reasons"])
                payment.status = "APPROVED"
                log_event(
                    db,
                    state["run_id"],
                    "AUTHORIZATION",
                    "Payment authorized",
                    {"source": authorization, "amount": float(payment.amount)},
                    commit=False,
                )

                result = execute_payment_tool(db, payment, commit=False)
                _log_tool(
                    db,
                    state["run_id"],
                    "execute_payment",
                    {"idempotency_key": payment.idempotency_key},
                    result,
                    commit=False,
                )

                account = get_account(db, state["session_id"], payment.account_id)
                run.status = "COMPLETED"
                auth_text = "automatically" if authorization == "auto" else "after human approval"
                run.summary = (
                    f"Payment completed {auth_text}. ₹{payment.amount:,.2f} sent to {payment.beneficiary}. "
                    f"Remaining {account.nickname} balance: ₹{account.balance:,.2f}."
                )
                log_event(
                    db,
                    state["run_id"],
                    "FINAL",
                    "Payment verified",
                    {
                        "transaction_id": result["transaction_id"],
                        "remaining_balance": float(account.balance),
                        "authorization": authorization,
                    },
                    commit=False,
                )
                db.commit()
                return {
                    "approval_status": authorization,
                    "transaction": result,
                    "summary": run.summary,
                    "route": "done",
                }
            except Exception as exc:
                db.rollback()
                payment = db.scalar(
                    select(PaymentRequest).where(PaymentRequest.run_id == state["run_id"])
                )
                run = db.get(AgentRun, state["run_id"])
                if payment and run and payment.status != "COMPLETED":
                    payment.status = "FAILED"
                    run.status = "FAILED"
                    run.summary = (
                        "Payment failed safely during simulated execution. "
                        "No successful transaction was recorded."
                    )
                    db.commit()
                    log_event(
                        db,
                        state["run_id"],
                        "ERROR",
                        "Payment execution failed safely",
                        {"error_type": type(exc).__name__},
                    )
                    return {
                        "approval_status": "failed",
                        "summary": run.summary,
                        "route": "done",
                    }
                raise


def auto_execute_node(state: AgentState) -> dict:
    return _execute_authorized(state, "auto")


def approval_and_execute(decision: str, state: AgentState) -> dict:
    if decision == "approve":
        return _execute_authorized(state, "human")

    with payment_execution_lock(state["session_id"]):
        with SessionLocal() as db:
            payment = db.scalar(
                select(PaymentRequest).where(PaymentRequest.run_id == state["run_id"])
            )
            if not payment:
                raise ValueError("No pending payment found")
            begin_serialized_payment_transaction(db, state["session_id"], payment.account_id)
            db.expire_all()
            payment = db.scalar(
                select(PaymentRequest).where(PaymentRequest.run_id == state["run_id"])
            )
            run = db.get(AgentRun, state["run_id"])
            if not payment or not run:
                db.rollback()
                raise ValueError("No pending payment found")

            terminal = _terminal_payment_result(db, payment, run)
            if terminal:
                db.rollback()
                return terminal

            if payment.status != "AWAITING_APPROVAL":
                db.rollback()
                raise ValueError(
                    f"Payment is not awaiting approval; current state is {payment.status}"
                )

            payment.status = "REJECTED"
            run.status = "REJECTED"
            run.summary = "Payment rejected by the human reviewer. No ledger change was made."
            log_event(
                db,
                state["run_id"],
                "APPROVAL",
                "Payment rejected",
                {"decision": decision},
                commit=False,
            )
            db.commit()
            return {
                "approval_status": "rejected",
                "summary": run.summary,
                "route": "done",
            }


class FallbackRuntime:
    mode = "fallback"

    def __init__(self, reason: str | None = None):
        self.reason = reason or "LangGraph runtime unavailable"

    def start(self, initial: AgentState) -> dict:
        state = dict(initial)
        state.update(parse_node(state))
        state.update(plan_node(state))
        route = route_after_plan(state)
        if route == "analysis":
            state.update(analysis_node(state))
            return state
        if route == "unknown":
            state.update(unknown_node(state))
            return state
        state.update(payment_context_node(state))
        state.update(evaluate_node(state))
        if state.get("route") == "auto_execute":
            state.update(auto_execute_node(state))
        return state

    def resume(self, run_id: str, session_id: str, decision: str) -> dict:
        with SessionLocal() as db:
            run = db.get(AgentRun, run_id)
            if not run or run.session_id != session_id:
                raise ValueError("Agent run no longer exists")
            account_id = run.account_id
        return approval_and_execute(
            decision,
            {"run_id": run_id, "session_id": session_id, "account_id": account_id},
        )

    def delete_threads(self, _run_ids: list[str]) -> None:
        return None

    def close(self) -> None:
        return None


class LangGraphRuntime:
    mode = "langgraph"
    reason = None

    def __init__(self, db_path: str | None = None):
        os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")
        from langgraph.checkpoint.sqlite import SqliteSaver
        from langgraph.graph import END, START, StateGraph
        from langgraph.types import Command, interrupt

        self.Command = Command
        self._checkpointer_cm = SqliteSaver.from_conn_string(db_path or settings.langgraph_db_path)
        self._checkpointer = self._checkpointer_cm.__enter__()
        self._closed = False
        atexit.register(self.close)

        def approval_node(state: AgentState):
            choice = interrupt(
                {
                    "run_id": state["run_id"],
                    "message": "Approve this simulated financial action?",
                }
            )
            return approval_and_execute(str(choice), state)

        builder = StateGraph(AgentState)
        for name, node in [
            ("parse", parse_node),
            ("plan", plan_node),
            ("analysis", analysis_node),
            ("unknown", unknown_node),
            ("payment_context", payment_context_node),
            ("evaluate", evaluate_node),
            ("approval", approval_node),
            ("auto_execute", auto_execute_node),
        ]:
            builder.add_node(name, node)
        builder.add_edge(START, "parse")
        builder.add_edge("parse", "plan")
        builder.add_conditional_edges(
            "plan",
            route_after_plan,
            {"analysis": "analysis", "payment": "payment_context", "unknown": "unknown"},
        )
        builder.add_edge("analysis", END)
        builder.add_edge("unknown", END)
        builder.add_edge("payment_context", "evaluate")
        builder.add_conditional_edges(
            "evaluate",
            route_after_evaluate,
            {"approval": "approval", "auto_execute": "auto_execute", "end": END},
        )
        builder.add_edge("approval", END)
        builder.add_edge("auto_execute", END)
        self.graph = builder.compile(checkpointer=self._checkpointer)

    def start(self, initial: AgentState) -> dict:
        return self.graph.invoke(
            initial,
            config={"configurable": {"thread_id": initial["run_id"]}},
        )

    def _run_account_id(self, run_id: str, session_id: str) -> int:
        with SessionLocal() as db:
            run = db.get(AgentRun, run_id)
            if not run or run.session_id != session_id:
                raise ValueError("Agent run no longer exists")
            return run.account_id

    def resume(self, run_id: str, session_id: str, decision: str) -> dict:
        config = {"configurable": {"thread_id": run_id}}
        get_tuple = getattr(self._checkpointer, "get_tuple", None)
        checkpoint = get_tuple(config) if callable(get_tuple) else True
        if checkpoint is None:
            # Domain state is the durable source of truth. If a deployment restart
            # loses the lightweight SQLite graph checkpoint but keeps the domain DB,
            # an already-persisted approval can still complete safely after the same
            # execution-time revalidation and idempotency checks.
            return approval_and_execute(
                decision,
                {"run_id": run_id, "session_id": session_id, "account_id": self._run_account_id(run_id, session_id)},
            )
        return self.graph.invoke(self.Command(resume=decision), config=config)

    def delete_threads(self, run_ids: list[str]) -> None:
        delete_thread = getattr(self._checkpointer, "delete_thread", None)
        if not callable(delete_thread):
            return
        for run_id in run_ids:
            try:
                delete_thread(run_id)
            except Exception:
                # Domain data is already removed; checkpoint cleanup is best-effort.
                continue

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._checkpointer_cm.__exit__(None, None, None)


def build_runtime():
    try:
        return LangGraphRuntime()
    except Exception as exc:
        return FallbackRuntime(reason=f"{type(exc).__name__}: {exc}")


runtime = build_runtime()
