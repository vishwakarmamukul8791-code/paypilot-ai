def test_new_session_is_completely_empty(client, fresh_session_headers):
    d=client.get('/api/dashboard',headers=fresh_session_headers).json()
    assert d['configured'] is False and d['balance']==0 and d['beneficiaries']==[] and d['bills']==[] and d['recent_transactions']==[] and d['transaction_count']==0
    assert client.get('/api/agent/runs',headers=fresh_session_headers).json()==[]

def test_agent_requires_user_created_account(client,fresh_session_headers):
    r=client.post('/api/agent/run',headers=fresh_session_headers,json={'message':'How much did I spend this month?'})
    assert r.status_code==409 and 'Create the simulation account first' in r.json()['detail']

def test_user_can_create_account_target_and_bill(client,fresh_session_headers):
    h=fresh_session_headers
    a=client.post('/api/account',headers=h,json={'owner_name':'Recruiter','opening_balance':42000,'daily_limit':30000}); assert a.status_code==200 and a.json()['balance']==42000
    t=client.post('/api/targets',headers=h,json={'name':'My Mobile','kind':'mobile_recharge','reference':'9876543210'}); assert t.status_code==200 and t.json()['kind']=='mobile_recharge'
    b=client.post('/api/bills',headers=h,json={'provider':'My Utility','amount':999,'due_date':'2026-08-30'}); assert b.status_code==200
    d=client.get('/api/dashboard',headers=h).json(); assert {x['name'] for x in d['beneficiaries']}=={'My Mobile','My Utility'} and d['bills'][0]['provider']=='My Utility'

def test_reset_returns_to_empty_state(client,session_headers):
    client.post('/api/demo/reset',headers=session_headers); d=client.get('/api/dashboard',headers=session_headers).json()
    assert d['configured'] is False and d['beneficiaries']==[] and d['bills']==[] and d['recent_transactions']==[]

def test_sessions_are_isolated(client):
    a=client.post('/api/demo/session').json()['session_id']; b=client.post('/api/demo/session').json()['session_id']; ha={'X-Demo-Session':a}; hb={'X-Demo-Session':b}
    assert client.post('/api/account',headers=ha,json={'owner_name':'User A','opening_balance':10000,'daily_limit':10000}).status_code==200
    assert client.get('/api/dashboard',headers=ha).json()['configured'] is True and client.get('/api/dashboard',headers=hb).json()['configured'] is False

def test_invalid_demo_session_header_is_rejected(client): assert client.get('/api/dashboard',headers={'X-Demo-Session':'../../bad/session'}).status_code==400

def test_duplicate_target_name_is_rejected(client,session_headers): assert client.post('/api/targets',headers=session_headers,json={'name':'Alpha Payee','kind':'other','reference':'XX'}).status_code==409

def test_agent_run_rate_limit_is_enforced(client,session_headers):
    for i in range(12): assert client.post('/api/agent/run',headers=session_headers,json={'message':f'Tell me a joke number {i}'}).status_code==200
    assert client.post('/api/agent/run',headers=session_headers,json={'message':'Tell me one more joke'}).status_code==429

def test_agent_run_detail_is_session_scoped(client,session_headers):
    other={'X-Demo-Session':client.post('/api/demo/session').json()['session_id']}; run=client.post('/api/agent/run',headers=session_headers,json={'message':'Pay ₹5,000 to Alpha Payee'}).json()
    assert client.get(f"/api/agent/runs/{run['run_id']}",headers=other).status_code==404

def test_other_session_cannot_approve_pending_run(client,session_headers):
    other={'X-Demo-Session':client.post('/api/demo/session').json()['session_id']}; run=client.post('/api/agent/run',headers=session_headers,json={'message':'Pay ₹5,000 to Alpha Payee'}).json()
    assert client.post(f"/api/agent/runs/{run['run_id']}/decision",headers=other,json={'decision':'approve'}).status_code==404


def test_stateful_endpoint_requires_demo_session_header(client):
    response = client.get('/api/dashboard')
    assert response.status_code == 400
    assert 'X-Demo-Session' in response.json()['detail']


def test_forged_uuid_does_not_implicitly_create_session(client):
    response = client.get('/api/dashboard', headers={'X-Demo-Session': '11111111-1111-4111-8111-111111111111'})
    assert response.status_code == 404
    assert 'expired or does not exist' in response.json()['detail']


def test_api_responses_send_security_and_no_store_headers(client, fresh_session_headers):
    response = client.get('/api/dashboard', headers=fresh_session_headers)
    assert response.status_code == 200
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert response.headers['x-frame-options'] == 'DENY'
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers.get('x-request-id')


def test_whitespace_only_setup_values_are_rejected(client, fresh_session_headers):
    response = client.post(
        '/api/account',
        headers=fresh_session_headers,
        json={'owner_name': '   ', 'opening_balance': 1000, 'daily_limit': 1000},
    )
    assert response.status_code == 422


def test_invalid_bill_date_is_rejected(client, session_headers):
    response = client.post(
        '/api/bills',
        headers=session_headers,
        json={'provider': 'Bad Date Utility', 'amount': 999, 'due_date': '2026-99-99'},
    )
    assert response.status_code == 422
