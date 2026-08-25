"""Public API smoke test.

Usage:
    python scripts/smoke_test.py http://localhost:8000

Creates all domain data through public APIs and validates session isolation,
auto execution, HITL approval, deterministic guardrails, and reset.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
import uuid

base = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")


def call(path: str, *, method: str = "GET", headers: dict | None = None, payload: dict | None = None):
    data = json.dumps(payload).encode() if payload is not None else None
    req_headers = {"Accept": "application/json", **(headers or {})}
    req = urllib.request.Request(base + path, data=data, headers=req_headers, method=method)
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.load(response), response.status, dict(response.headers)


def expect_http(path: str, status: int, *, headers: dict | None = None):
    try:
        call(path, headers=headers)
    except urllib.error.HTTPError as exc:
        assert exc.code == status, (exc.code, exc.read().decode())
        return
    raise AssertionError(f"Expected HTTP {status} for {path}")


ready, status, _ = call("/ready")
assert status == 200 and ready["database"] == "ok", ready
health, _, health_headers = call("/health")
assert health["status"] in {"healthy", "degraded"}, health
assert health["real_money"] is False, health
assert {k.lower(): v for k, v in health_headers.items()}.get("x-request-id"), health_headers
print("HEALTH", health["status"], health["agent_runtime"], "gemini=", health["gemini_configured"])
if health["agent_runtime"] != "langgraph":
    print("WARNING: full LangGraph runtime is unavailable:", health.get("runtime_fallback_reason"))

# Stateful endpoints must not create a forged session as a side effect.
forged_headers = {"X-Demo-Session": str(uuid.uuid4())}
expect_http("/api/dashboard", 404, headers=forged_headers)

session, _, _ = call("/api/demo/session", method="POST")
headers = {"X-Demo-Session": session["session_id"], "Content-Type": "application/json"}

empty, _, _ = call("/api/dashboard", headers=headers)
assert empty["configured"] is False, empty
assert empty["transaction_count"] == 0, empty
assert empty["beneficiaries"] == [], empty
assert empty["bills"] == [], empty

main_account, _, _ = call(
    "/api/accounts",
    method="POST",
    headers=headers,
    payload={"owner_name": "Smoke User", "nickname": "Main", "account_type": "savings", "opening_balance": 60000, "daily_limit": 50000},
)
travel_state, _, _ = call(
    "/api/accounts",
    method="POST",
    headers=headers,
    payload={"owner_name": "Smoke User", "nickname": "Travel", "account_type": "wallet", "opening_balance": 10000, "daily_limit": 10000},
)
travel_id = next(a["id"] for a in travel_state["accounts"] if a["nickname"] == "Travel")
main_id = next(a["id"] for a in travel_state["accounts"] if a["nickname"] == "Main")
transferred, _, _ = call(
    "/api/accounts/transfer",
    method="POST",
    headers=headers,
    payload={
        "source_account_id": main_id,
        "destination_account_id": travel_id,
        "amount": 1000,
        "idempotency_key": "smoke-transfer-001",
    },
)
assert next(a for a in transferred["accounts"] if a["id"] == travel_id)["balance"] == 11000
call(
    "/api/targets",
    method="POST",
    headers=headers,
    payload={"name": "Smoke Mobile", "kind": "mobile_recharge", "reference": "98XXXXXX01"},
)
call(
    "/api/targets",
    method="POST",
    headers=headers,
    payload={"name": "Smoke Merchant", "kind": "merchant_payment", "reference": "MERCHANT-SMOKE"},
)

auto, _, _ = call(
    "/api/agent/run",
    method="POST",
    headers=headers,
    payload={"message": "Recharge Smoke Mobile for ₹499", "source_account_id": travel_id},
)
assert auto["status"] == "COMPLETED", auto
assert auto["payment"]["transaction_id"].startswith("PPA-"), auto
assert auto["source_account"] == "Travel", auto

pending, _, _ = call(
    "/api/agent/run",
    method="POST",
    headers=headers,
    payload={"message": "Pay ₹12,000 to Smoke Merchant"},
)
assert pending["status"] == "AWAITING_APPROVAL", pending
assert pending["payment"]["risk_level"] == "MEDIUM", pending

done, _, _ = call(
    f"/api/agent/runs/{pending['run_id']}/decision",
    method="POST",
    headers=headers,
    payload={"decision": "approve"},
)
assert done["status"] == "COMPLETED", done

blocked, _, _ = call(
    "/api/agent/run",
    method="POST",
    headers=headers,
    payload={"message": "Do not pay ₹500 to Smoke Merchant"},
)
assert blocked["status"] == "BLOCKED", blocked
assert blocked["payment"] is None, blocked

call("/api/demo/reset", method="POST", headers=headers)
reset, _, _ = call("/api/dashboard", headers=headers)
assert reset["configured"] is False, reset
assert reset["transaction_count"] == 0, reset
assert reset["beneficiaries"] == [], reset
assert reset["bills"] == [], reset

print(
    "PASS",
    "auto_txn=", auto["payment"]["transaction_id"],
    "approved_txn=", done["payment"]["transaction_id"],
)
