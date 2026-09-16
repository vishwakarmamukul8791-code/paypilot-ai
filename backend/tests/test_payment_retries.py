from concurrent.futures import ThreadPoolExecutor

import pytest


def start(client, headers, message, operation_id="review-operation-001", **extra):
    return client.post("/api/agent/run", headers=headers, json={
        "message": message, "operation_id": operation_id, **extra,
    })


@pytest.mark.parametrize("condition", ["only if I approve", "ask me first", "confirm with me first", "only after I confirm"])
def test_explicit_approval_prevents_small_payment_auto_execution(client, session_headers, condition):
    response = start(client, session_headers, f"Pay ₹100 to Alpha Payee {condition}")
    assert response.status_code == 200
    run = response.json()
    assert run["status"] == "AWAITING_APPROVAL"
    assert run["payment"]["conditions"]["requires_approval"] is True
    assert client.get("/api/dashboard", headers=session_headers).json()["balance"] == 75000
    approved = client.post(f"/api/agent/runs/{run['run_id']}/decision", headers=session_headers, json={"decision": "approve"})
    assert approved.json()["status"] == "COMPLETED"
    assert client.get("/api/dashboard", headers=session_headers).json()["balance"] == 74900


def test_unknown_payment_condition_is_not_discarded(client, session_headers):
    result = start(client, session_headers, "Pay ₹100 to Alpha Payee only if my manager agrees")
    assert result.json()["status"] == "BLOCKED"
    assert client.get("/api/dashboard", headers=session_headers).json()["balance"] == 75000


def test_operation_retry_returns_same_run_and_single_debit(client, session_headers):
    first = start(client, session_headers, "Pay ₹100 to Alpha Payee")
    retry = start(client, session_headers, "Pay ₹100 to Alpha Payee")
    assert first.status_code == retry.status_code == 200
    assert first.json()["run_id"] == retry.json()["run_id"]
    assert client.get("/api/dashboard", headers=session_headers).json()["balance"] == 74900


def test_operation_id_cannot_be_reused_with_changed_payload(client, session_headers):
    start(client, session_headers, "Pay ₹100 to Alpha Payee")
    assert start(client, session_headers, "Pay ₹200 to Alpha Payee").status_code == 409
    assert client.get("/api/dashboard", headers=session_headers).json()["balance"] == 74900


def test_new_operation_can_repeat_same_payment(client, session_headers):
    start(client, session_headers, "Pay ₹100 to Alpha Payee")
    second = start(client, session_headers, "Pay ₹100 to Alpha Payee", "review-operation-002")
    assert second.json()["status"] == "COMPLETED"
    assert client.get("/api/dashboard", headers=session_headers).json()["balance"] == 74800


def test_concurrent_operation_retries_create_one_payment(client, session_headers):
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: start(client, session_headers, "Pay ₹100 to Alpha Payee"), range(3)))
    assert all(result.status_code == 200 for result in results)
    assert len({result.json()["run_id"] for result in results}) == 1
    assert client.get("/api/dashboard", headers=session_headers).json()["balance"] == 74900


def test_retry_keeps_same_pending_approval(client, session_headers):
    first = start(client, session_headers, "Pay ₹5000 to Alpha Payee").json()
    retry = start(client, session_headers, "Pay ₹5000 to Alpha Payee").json()
    assert first["run_id"] == retry["run_id"]
    assert retry["status"] == "AWAITING_APPROVAL"
