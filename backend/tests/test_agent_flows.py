from concurrent.futures import ThreadPoolExecutor
import pytest


def start(client,h,message):
    r=client.post('/api/agent/run',headers=h,json={'message':message}); assert r.status_code==200,r.text; return r.json()
def decide(client,h,run,decision): return client.post(f"/api/agent/runs/{run['run_id']}/decision",headers=h,json={'decision':decision})

def test_up_to_2000_auto_executes_without_human_approval(client,session_headers):
    run=start(client,session_headers,'Pay ₹2,000 to Alpha Payee'); assert run['status']=='COMPLETED' and run['payment']['status']=='COMPLETED'; assert any(e['kind']=='AUTO_AUTHORIZATION' for e in run['events']); assert client.get('/api/dashboard',headers=session_headers).json()['balance']==73000

def test_above_2000_requires_human_approval(client,session_headers):
    run=start(client,session_headers,'Pay ₹5,000 to Alpha Payee'); assert run['status']=='AWAITING_APPROVAL' and run['payment']['status']=='AWAITING_APPROVAL'; assert client.get('/api/dashboard',headers=session_headers).json()['balance']==75000

def test_explicit_confirmation_can_require_approval_below_2000(client,session_headers): assert start(client,session_headers,'Pay ₹1,500 to Alpha Payee but ask me if it is above ₹1,000')['status']=='AWAITING_APPROVAL'

def test_approve_changes_ledger(client,session_headers):
    run=start(client,session_headers,'Pay ₹5,000 to Alpha Payee'); done=decide(client,session_headers,run,'approve'); assert done.status_code==200 and done.json()['status']=='COMPLETED'; assert client.get('/api/dashboard',headers=session_headers).json()['balance']==70000

def test_reject_does_not_change_ledger(client,session_headers):
    run=start(client,session_headers,'Pay ₹5,000 to Alpha Payee'); assert decide(client,session_headers,run,'reject').json()['status']=='REJECTED'; assert client.get('/api/dashboard',headers=session_headers).json()['balance']==75000

def test_unknown_destination_is_blocked_not_invented(client,session_headers):
    run=start(client,session_headers,'Pay ₹5,000 to Never Created'); assert run['status']=='BLOCKED' and run['payment'] is None and 'has not been created' in run['summary']

def test_minimum_balance_policy_blocks(client,session_headers):
    run=start(client,session_headers,'Pay ₹20,000 to Alpha Payee but leave at least ₹60,000 in my account'); assert run['status']=='BLOCKED' and run['payment']['status']=='BLOCKED'

def test_low_risk_band_is_fixed_through_10000(client,session_headers):
    run=start(client,session_headers,'Pay ₹10,000 to Alpha Payee'); assert run['payment']['risk_level']=='LOW' and run['payment']['risk_score']==20

def test_medium_risk_band_is_fixed_above_10000_through_50000(client,session_headers):
    run=start(client,session_headers,'Pay ₹12,000 to Alpha Payee'); assert run['status']=='AWAITING_APPROVAL' and run['payment']['risk_level']=='MEDIUM' and run['payment']['risk_score']==60

def test_mobile_recharge_is_generic_user_created_payment_type(client,session_headers):
    assert start(client,session_headers,'Recharge Mobile One for ₹499')['status']=='COMPLETED'; assert client.get('/api/transactions',headers=session_headers).json()[0]['category']=='mobile_recharge'

def test_merchant_payment_uses_user_defined_type(client,session_headers):
    assert start(client,session_headers,'Pay ₹1,999 to Merchant One')['status']=='COMPLETED'; assert client.get('/api/transactions',headers=session_headers).json()[0]['category']=='merchant_payment'

def test_arbitrary_custom_transaction_type_is_supported(client,session_headers):
    assert client.post('/api/targets',headers=session_headers,json={'name':'Community Fund','kind':'donation','reference':'CF-1'}).status_code==200; assert start(client,session_headers,'Pay ₹750 to Community Fund')['status']=='COMPLETED'; assert client.get('/api/transactions',headers=session_headers).json()[0]['category']=='donation'

def test_bill_above_2000_requires_approval(client,session_headers):
    run=start(client,session_headers,'Pay my Utility One bill'); assert run['status']=='AWAITING_APPROVAL' and run['payment']['beneficiary']=='Utility One' and run['payment']['amount']==3480

def test_small_user_created_bill_auto_executes(client,session_headers):
    assert client.post('/api/bills',headers=session_headers,json={'provider':'Small Utility','amount':1200,'due_date':'2026-08-30'}).status_code==200; assert start(client,session_headers,'Pay my Small Utility bill')['status']=='COMPLETED'; bills=client.get('/api/dashboard',headers=session_headers).json()['bills']; assert next(b for b in bills if b['provider']=='Small Utility')['status']=='PAID'

def test_partial_bill_amount_is_blocked(client,session_headers):
    run=start(client,session_headers,'Pay ₹1 Utility One bill'); assert run['status']=='BLOCKED'; assert next(b for b in client.get('/api/dashboard',headers=session_headers).json()['bills'] if b['provider']=='Utility One')['status']=='PENDING'

def test_spending_analysis_uses_only_session_created_transactions(client,session_headers):
    start(client,session_headers,'Pay ₹500 to Alpha Payee'); run=start(client,session_headers,'How much did I spend this month?'); assert run['status']=='COMPLETED' and '₹500.00' in run['summary']

def test_unusual_analysis_surfaces_medium_risk_payment_created_in_session(client,session_headers):
    p=start(client,session_headers,'Pay ₹12,000 to Alpha Payee'); assert decide(client,session_headers,p,'approve').json()['status']=='COMPLETED'; run=start(client,session_headers,'Are there any unusual transactions this month?'); assert run['status']=='COMPLETED' and '1 medium/high-risk' in run['summary']

def test_unknown_non_banking_request_is_safe(client,session_headers): assert start(client,session_headers,'Write a poem about Delhi')['status']=='BLOCKED'

def test_cannot_decide_on_auto_executed_payment(client,session_headers):
    run=start(client,session_headers,'Pay ₹2,000 to Alpha Payee'); assert decide(client,session_headers,run,'approve').status_code==409

@pytest.mark.parametrize('amount',[1,100,500,999,1500,2000])
def test_auto_execute_boundary(client,session_headers,amount): assert start(client,session_headers,f'Pay ₹{amount} to Alpha Payee')['status']=='COMPLETED'

@pytest.mark.parametrize('amount',[2000.01,2500,5000,10000,12000])
def test_human_approval_boundary(client,session_headers,amount): assert start(client,session_headers,f'Pay ₹{amount} to Alpha Payee')['status']=='AWAITING_APPROVAL'

def test_negated_payment_is_blocked(client,session_headers): assert start(client,session_headers,'Do not pay ₹500 to Alpha Payee')['status']=='BLOCKED'
def test_multiple_payments_are_blocked(client,session_headers): assert start(client,session_headers,'Pay ₹500 to Alpha Payee and ₹500 to Mobile One')['status']=='BLOCKED'
def test_scheduled_payment_is_blocked(client,session_headers): assert start(client,session_headers,'Pay ₹500 to Alpha Payee tomorrow')['status']=='BLOCKED'

def test_minimum_balance_is_revalidated_after_another_payment(client,session_headers):
    protected=start(client,session_headers,'Pay ₹20,000 to Alpha Payee but leave at least ₹50,000 in my account'); other=start(client,session_headers,'Pay ₹20,000 to Merchant One'); assert decide(client,session_headers,other,'approve').json()['status']=='COMPLETED'; assert decide(client,session_headers,protected,'approve').json()['status']=='BLOCKED'; assert client.get('/api/dashboard',headers=session_headers).json()['balance']==55000

def test_daily_limit_is_revalidated_across_pending_approvals(client,session_headers):
    runs=[start(client,session_headers,'Pay ₹18,000 to Alpha Payee'),start(client,session_headers,'Pay ₹18,000 to Mobile One'),start(client,session_headers,'Pay ₹18,000 to Merchant One')]; assert decide(client,session_headers,runs[0],'approve').json()['status']=='COMPLETED'; assert decide(client,session_headers,runs[1],'approve').json()['status']=='COMPLETED'; assert decide(client,session_headers,runs[2],'approve').json()['status']=='BLOCKED'; assert client.get('/api/dashboard',headers=session_headers).json()['balance']==39000

def test_fractional_auto_payments_keep_precision(client,session_headers):
    assert start(client,session_headers,'Pay ₹0.10 to Alpha Payee')['status']=='COMPLETED'; assert start(client,session_headers,'Pay ₹0.20 to Mobile One')['status']=='COMPLETED'; assert client.get('/api/dashboard',headers=session_headers).json()['balance']==74999.7

def test_concurrent_approvals_cannot_overspend_daily_limit(client,session_headers):
    runs=[start(client,session_headers,'Pay ₹18,000 to Alpha Payee'),start(client,session_headers,'Pay ₹18,000 to Mobile One'),start(client,session_headers,'Pay ₹18,000 to Merchant One')]
    with ThreadPoolExecutor(max_workers=3) as pool: statuses=list(pool.map(lambda run:decide(client,session_headers,run,'approve').json()['status'],runs))
    assert statuses.count('COMPLETED')==2 and statuses.count('BLOCKED')==1 and client.get('/api/dashboard',headers=session_headers).json()['balance']==39000

def test_foreign_currency_is_blocked(client,session_headers): assert start(client,session_headers,'Pay $500 to Alpha Payee')['status']=='BLOCKED'


def test_high_risk_request_above_50000_escalates_to_human_approval(client,fresh_session_headers):
    h = fresh_session_headers
    assert client.post('/api/account', headers=h, json={'owner_name':'High Risk Tester','opening_balance':150000,'daily_limit':100000}).status_code == 200
    assert client.post('/api/targets', headers=h, json={'name':'Alpha Payee','kind':'transfer','reference':'HIGH-001'}).status_code == 200
    run=start(client,h,'Pay ₹60,000 to Alpha Payee')
    assert run['status']=='AWAITING_APPROVAL'
    assert run['payment']['risk_level']=='HIGH' and run['payment']['risk_score']==90


def test_platform_cap_still_blocks_amount_above_100000(
    client,
    fresh_session_headers,
):
    h = fresh_session_headers

    assert client.post(
        '/api/account',
        headers=h,
        json={
            'owner_name': 'Cap Tester',
            'opening_balance': 200000,
            'daily_limit': 200000,
        },
    ).status_code == 200

    assert client.post(
        '/api/targets',
        headers=h,
        json={
            'name': 'Alpha Payee',
            'kind': 'transfer',
            'reference': 'CAP-001',
        },
    ).status_code == 200

    run = start(
        client,
        h,
        'Pay ₹1,20,000 to Alpha Payee',
    )

    assert run['status'] == 'BLOCKED'
    assert 'Per-payment demo limit is ₹100,000' in run['summary']

def test_pending_payment_blocks_safely_if_destination_is_removed_before_approval(client,session_headers):
    run=start(client,session_headers,'Pay ₹5,000 to Alpha Payee')
    assert run['status']=='AWAITING_APPROVAL'
    deleted=client.delete('/api/targets/Alpha Payee',headers=session_headers)
    assert deleted.status_code==200
    result=decide(client,session_headers,run,'approve')
    assert result.status_code==200 and result.json()['status']=='BLOCKED'
    assert client.get('/api/dashboard',headers=session_headers).json()['balance']==75000


def test_concurrent_duplicate_approval_executes_only_once(client, session_headers):
    run = start(client, session_headers, 'Pay ₹5,000 to Alpha Payee')
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda _: decide(client, session_headers, run, 'approve'),
                range(2),
            )
        )
    assert all(response.status_code == 200 for response in responses)
    assert all(response.json()['status'] == 'COMPLETED' for response in responses)
    dashboard = client.get('/api/dashboard', headers=session_headers).json()
    transactions = client.get('/api/transactions', headers=session_headers).json()
    assert dashboard['balance'] == 70000
    assert len(transactions) == 1


def test_execution_failure_rolls_back_ledger_and_transaction(client, session_headers, monkeypatch):
    import importlib

    runtime_module = importlib.import_module('app.agents.runtime')
    original = runtime_module._log_tool

    def fail_after_execution(db, run_id, name, args, result, *, commit=True):
        if name == 'execute_payment':
            raise RuntimeError('synthetic post-ledger failure')
        return original(db, run_id, name, args, result, commit=commit)

    monkeypatch.setattr(runtime_module, '_log_tool', fail_after_execution)
    run = start(client, session_headers, 'Pay ₹500 to Alpha Payee')

    assert run['status'] == 'FAILED'
    dashboard = client.get('/api/dashboard', headers=session_headers).json()
    transactions = client.get('/api/transactions', headers=session_headers).json()
    assert dashboard['balance'] == 75000
    assert transactions == []
