
def create_second(client, headers, nickname='Travel', balance=12000, daily_limit=8000):
    response = client.post(
        '/api/accounts',
        headers=headers,
        json={
            'owner_name': 'Test User',
            'nickname': nickname,
            'account_type': 'wallet',
            'opening_balance': balance,
            'daily_limit': daily_limit,
        },
    )
    assert response.status_code == 200, response.text
    return next(a for a in response.json()['accounts'] if a['nickname'] == nickname)


def test_multiple_accounts_are_supported_and_primary_is_stable(client, session_headers):
    second = create_second(client, session_headers)
    dashboard = client.get('/api/dashboard', headers=session_headers).json()
    assert len(dashboard['accounts']) == 2
    assert dashboard['primary_account_id'] != second['id']
    assert dashboard['balance'] == 75000
    assert dashboard['total_balance'] == 87000


def test_account_can_be_edited_and_made_primary(client, session_headers):
    second = create_second(client, session_headers)
    edited = client.patch(
        f"/api/accounts/{second['id']}",
        headers=session_headers,
        json={
            'owner_name': 'Test User',
            'nickname': 'Trips',
            'account_type': 'savings',
            'daily_limit': 9000,
            'is_active': True,
        },
    )
    assert edited.status_code == 200, edited.text
    account = next(a for a in edited.json()['accounts'] if a['id'] == second['id'])
    assert account['nickname'] == 'Trips' and account['daily_limit'] == 9000
    primary = client.post(f"/api/accounts/{second['id']}/primary", headers=session_headers)
    assert primary.status_code == 200
    assert primary.json()['primary_account_id'] == second['id']
    assert primary.json()['balance'] == 12000


def test_add_money_is_ledgered_not_silent_balance_edit(client, session_headers):
    second = create_second(client, session_headers)
    response = client.post(f"/api/accounts/{second['id']}/funds", headers=session_headers, json={'amount': 2500.25})
    assert response.status_code == 200, response.text
    account = next(a for a in response.json()['accounts'] if a['id'] == second['id'])
    assert account['balance'] == 14500.25
    txns = client.get('/api/transactions', headers=session_headers).json()
    credit = next(t for t in txns if t['account_id'] == second['id'])
    assert credit['direction'] == 'CREDIT' and credit['category'] == 'add_money' and credit['amount'] == 2500.25


def test_agent_debits_only_selected_source_account(client, session_headers):
    second = create_second(client, session_headers, balance=10000, daily_limit=10000)
    run = client.post(
        '/api/agent/run',
        headers=session_headers,
        json={'message': 'Pay ₹1,500 to Alpha Payee', 'source_account_id': second['id']},
    )
    assert run.status_code == 200, run.text
    payload = run.json()
    assert payload['status'] == 'COMPLETED'
    assert payload['account_id'] == second['id']
    assert payload['source_account'] == 'Travel'
    dashboard = client.get('/api/dashboard', headers=session_headers).json()
    primary = next(a for a in dashboard['accounts'] if a['is_primary'])
    travel = next(a for a in dashboard['accounts'] if a['id'] == second['id'])
    assert primary['balance'] == 75000
    assert travel['balance'] == 8500


def test_paused_account_cannot_start_agent_payment(client, session_headers):
    second = create_second(client, session_headers)
    paused = client.patch(
        f"/api/accounts/{second['id']}",
        headers=session_headers,
        json={
            'owner_name': 'Test User',
            'nickname': 'Travel',
            'account_type': 'wallet',
            'daily_limit': 8000,
            'is_active': False,
        },
    )
    assert paused.status_code == 200
    run = client.post('/api/agent/run', headers=session_headers, json={'message': 'Pay ₹500 to Alpha Payee', 'source_account_id': second['id']})
    assert run.status_code == 409 and 'paused' in run.json()['detail'].lower()


def test_payee_and_pending_bill_are_editable(client, session_headers):
    target = next(t for t in client.get('/api/dashboard', headers=session_headers).json()['beneficiaries'] if t['name'] == 'Alpha Payee')
    changed = client.patch(
        f"/api/targets/{target['id']}",
        headers=session_headers,
        json={'name': 'Alpha Updated', 'kind': 'upi', 'reference': 'alpha@upi'},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()['name'] == 'Alpha Updated' and changed.json()['kind'] == 'upi'

    bill = next(b for b in client.get('/api/dashboard', headers=session_headers).json()['bills'] if b['provider'] == 'Utility One')
    bill_changed = client.patch(
        f"/api/bills/{bill['id']}",
        headers=session_headers,
        json={'provider': 'Utility Prime', 'amount': 3499, 'due_date': '2026-08-31'},
    )
    assert bill_changed.status_code == 200, bill_changed.text
    assert bill_changed.json()['provider'] == 'Utility Prime' and bill_changed.json()['amount'] == 3499


def test_account_daily_limit_can_support_high_risk_demo_band(client, fresh_session_headers):
    response = client.post(
        '/api/accounts',
        headers=fresh_session_headers,
        json={
            'owner_name': 'Test User',
            'nickname': 'High Limit',
            'account_type': 'savings',
            'opening_balance': 150000,
            'daily_limit': 100000,
        },
    )
    assert response.status_code == 200, response.text
    account = next(a for a in response.json()['accounts'] if a['nickname'] == 'High Limit')
    assert account['daily_limit'] == 100000

    too_high = client.patch(
        f"/api/accounts/{account['id']}",
        headers=fresh_session_headers,
        json={
            'owner_name': 'Test User',
            'nickname': 'High Limit',
            'account_type': 'savings',
            'daily_limit': 200000.01,
            'is_active': True,
        },
    )
    assert too_high.status_code == 422


def test_duplicate_payment_reference_is_rejected_for_same_type(client, session_headers):
    response = client.post(
        '/api/targets',
        headers=session_headers,
        json={'name': 'Duplicate Ref', 'kind': 'transfer', 'reference': 'test-001'},
    )
    assert response.status_code == 409
    assert "already saved for 'Alpha Payee'" in response.json()['detail']


def test_editing_payee_cannot_take_another_payees_reference(client, session_headers):
    dashboard = client.get('/api/dashboard', headers=session_headers).json()
    mobile = next(t for t in dashboard['beneficiaries'] if t['name'] == 'Mobile One')
    response = client.patch(
        f"/api/targets/{mobile['id']}",
        headers=session_headers,
        json={'name': 'Mobile One', 'kind': 'transfer', 'reference': 'TEST-001'},
    )
    assert response.status_code == 409
    assert "already saved for 'Alpha Payee'" in response.json()['detail']
