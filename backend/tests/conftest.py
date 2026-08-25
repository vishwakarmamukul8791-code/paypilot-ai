from __future__ import annotations

import os
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_TEST_ROOT = Path(tempfile.gettempdir()) / f"paypilot-tests-{os.getpid()}"
_TEST_ROOT.mkdir(parents=True, exist_ok=True)
_TEST_DB = _TEST_ROOT / "paypilot-test.db"
_TEST_GRAPH = _TEST_ROOT / "langgraph-test.db"
for path in [_TEST_DB, _TEST_GRAPH, Path(str(_TEST_GRAPH) + "-shm"), Path(str(_TEST_GRAPH) + "-wal")]: path.unlink(missing_ok=True)

os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
os.environ["LANGGRAPH_DB_PATH"] = str(_TEST_GRAPH)
os.environ.pop("GEMINI_API_KEY", None)
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def reset_in_process_rate_limiters():
    from app.services.rate_limit_service import global_agent_limiter, session_create_limiter
    global_agent_limiter.reset()
    session_create_limiter.reset()
    yield

@pytest.fixture
def client():
    with TestClient(app) as c: yield c

@pytest.fixture
def fresh_session_headers(client):
    r = client.post('/api/demo/session'); assert r.status_code == 200
    return {'X-Demo-Session': r.json()['session_id']}

@pytest.fixture
def session_headers(client, fresh_session_headers):
    h = fresh_session_headers
    assert client.post('/api/account', headers=h, json={'owner_name':'Test User','opening_balance':75000,'daily_limit':50000}).status_code == 200
    for payload in [
        {'name':'Alpha Payee','kind':'transfer','reference':'TEST-001'},
        {'name':'Mobile One','kind':'mobile_recharge','reference':'9000000001'},
        {'name':'Merchant One','kind':'merchant_payment','reference':'merchant@test'},
    ]: assert client.post('/api/targets', headers=h, json=payload).status_code == 200
    assert client.post('/api/bills', headers=h, json={'provider':'Utility One','amount':3480,'due_date':(date.today()+timedelta(days=5)).isoformat()}).status_code == 200
    return h
