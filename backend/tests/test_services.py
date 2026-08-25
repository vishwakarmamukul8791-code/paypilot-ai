from decimal import Decimal
import pytest
from app.database.db import SessionLocal
from app.models import Account,Beneficiary
from app.schemas.agent import PaymentConditions
from app.services.banking_service import find_beneficiary,get_account
from app.services.policy_service import evaluate_payment_policy
from app.services.risk_service import calculate_risk
from app.services.session_service import ensure_demo_session

def create_state(db,sid='service-test'):
    ensure_demo_session(db,sid)
    if not db.query(Account).filter(Account.session_id==sid).one_or_none():
        db.add(Account(session_id=sid,owner_name='Test',masked_account='SIM-TEST',balance=Decimal('75000'),daily_limit=Decimal('50000'))); db.add(Beneficiary(session_id=sid,name='Target One',kind='transfer',verified=True,account_mask='TEST')); db.commit()
    return find_beneficiary(db,sid,'Target One')

def test_no_account_is_created_by_session_creation():
    with SessionLocal() as db:
        ensure_demo_session(db,'service-empty-test')
        with pytest.raises(ValueError): get_account(db,'service-empty-test')

def test_policy_is_deterministic_for_same_state():
    with SessionLocal() as db:
        b=create_state(db,'service-policy-test'); r1=calculate_risk(db,'service-policy-test',1000,b); r2=calculate_risk(db,'service-policy-test',1000,b)
        assert r1==r2 and evaluate_payment_policy(db,'service-policy-test',1000,b,PaymentConditions(),r1)==evaluate_payment_policy(db,'service-policy-test',1000,b,PaymentConditions(),r2)

@pytest.mark.parametrize('amount,level,score',[(1,'LOW',20),(10000,'LOW',20),(10000.01,'MEDIUM',60),(50000,'MEDIUM',60),(50000.01,'HIGH',90)])
def test_fixed_risk_bands(amount,level,score):
    with SessionLocal() as db:
        b=create_state(db,f'risk-{amount}'); r=calculate_risk(db,f'risk-{amount}',amount,b); assert r['level']==level and r['score']==score

def test_expired_demo_sessions_are_cleaned_up():
    from datetime import datetime,timedelta,timezone
    from app.models import DemoSession
    from app.services.session_service import cleanup_expired_demo_sessions
    sid='expired-session-test'
    with SessionLocal() as db:
        ensure_demo_session(db,sid); s=db.get(DemoSession,sid); s.updated_at=datetime.now(timezone.utc)-timedelta(hours=30); db.commit(); cleanup_expired_demo_sessions(db); assert db.get(DemoSession,sid) is None
