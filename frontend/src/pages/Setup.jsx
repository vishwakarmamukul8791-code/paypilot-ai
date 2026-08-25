import { useMemo, useState } from 'react'

const money = (v) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(v || 0)
const emptyAccount = { owner_name: '', nickname: '', account_type: 'savings', opening_balance: '', daily_limit: '' }
const emptyTarget = { name: '', kind: 'transfer', reference: '' }
const emptyBill = { provider: '', amount: '', due_date: '' }

export default function Setup({ data, busy, error, actions, onTryPrompt }) {
  const [section, setSection] = useState('accounts')
  const [account, setAccount] = useState(emptyAccount)
  const [editingAccountId, setEditingAccountId] = useState(null)
  const [transferSourceId, setTransferSourceId] = useState(null)
  const [transferDestinationId, setTransferDestinationId] = useState('')
  const [transferAmount, setTransferAmount] = useState('')
  const [target, setTarget] = useState(emptyTarget)
  const [editingTargetId, setEditingTargetId] = useState(null)
  const [bill, setBill] = useState(emptyBill)
  const [editingBillId, setEditingBillId] = useState(null)

  const accounts = useMemo(() => data?.accounts || [], [data?.accounts])

  const targets = useMemo(
    () => data?.beneficiaries || [],
    [data?.beneficiaries],
)

const bills = useMemo(() => data?.bills || [], [data?.bills])
  const counts = useMemo(() => ({ accounts: accounts.length, payees: targets.length, bills: bills.filter((b) => b.status === 'PENDING').length }), [accounts, targets, bills])

  const submitAccount = async (e) => {
    e.preventDefault()
    let ok
    if (editingAccountId) {
      ok = await actions.updateAccount(editingAccountId, {
        owner_name: account.owner_name,
        nickname: account.nickname,
        account_type: account.account_type,
        daily_limit: Number(account.daily_limit),
        is_active: account.is_active !== false,
      })
    } else {
      ok = await actions.createAccount({ ...account, opening_balance: Number(account.opening_balance), daily_limit: Number(account.daily_limit) })
    }
    if (ok) { setAccount(emptyAccount); setEditingAccountId(null) }
  }

  const editAccount = (item) => {
    setEditingAccountId(item.id)
    setAccount({ owner_name: item.owner_name, nickname: item.nickname, account_type: item.account_type, opening_balance: '', daily_limit: item.daily_limit, is_active: item.is_active })
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const openTransfer = (sourceId) => {
    const destination = accounts.find((item) => item.id !== sourceId && item.is_active)
    setTransferSourceId(sourceId)
    setTransferDestinationId(destination ? String(destination.id) : '')
    setTransferAmount('')
  }

  const submitTransfer = async (e) => {
    e.preventDefault()
    if (!transferSourceId || !transferDestinationId || !transferAmount) return
    const idempotencyKey = globalThis.crypto?.randomUUID?.() || `web-${Date.now()}-${Math.random().toString(16).slice(2)}`
    const ok = await actions.transferFunds(
      transferSourceId,
      Number(transferDestinationId),
      Number(transferAmount),
      idempotencyKey,
    )
    if (ok) { setTransferSourceId(null); setTransferDestinationId(''); setTransferAmount('') }
  }

  const submitTarget = async (e) => {
    e.preventDefault()
    const ok = editingTargetId ? await actions.updateTarget(editingTargetId, target) : await actions.createTarget(target)
    if (ok) { setTarget(emptyTarget); setEditingTargetId(null) }
  }

  const editTarget = (item) => { setEditingTargetId(item.id); setTarget({ name: item.name, kind: item.kind, reference: item.reference }) }

  const submitBill = async (e) => {
    e.preventDefault()
    const payload = { ...bill, amount: Number(bill.amount) }
    const ok = editingBillId ? await actions.updateBill(editingBillId, payload) : await actions.createBill(payload)
    if (ok) { setBill(emptyBill); setEditingBillId(null) }
  }

  const editBill = (item) => { setEditingBillId(item.id); setBill({ provider: item.provider, amount: item.amount, due_date: item.due_date }) }

  return (
    <div className="page-stack manage-page">
      <section className="manage-header">
        <div><span className="section-kicker">PAYMENT SETTINGS</span><h1>Manage your simulation</h1><p>Accounts, payees and bills stay editable until ledger or approval integrity requires them to be immutable.</p></div>
        <div className="manage-stats"><div><strong>{counts.accounts}</strong><span>Accounts</span></div><div><strong>{counts.payees}</strong><span>Payees</span></div><div><strong>{counts.bills}</strong><span>Pending bills</span></div></div>
      </section>
      {error && <div className="error-box">{error}</div>}
      <div className="manage-tabs"><button className={section === 'accounts' ? 'active' : ''} onClick={() => setSection('accounts')}>Accounts</button><button className={section === 'payees' ? 'active' : ''} onClick={() => setSection('payees')}>Payees</button><button className={section === 'bills' ? 'active' : ''} onClick={() => setSection('bills')}>Bills</button></div>

      {section === 'accounts' && <div className="manage-grid">
        <section className="panel form-panel">
          <div className="section-title"><div><span className="section-kicker">{editingAccountId ? 'EDIT ACCOUNT' : 'ADD ACCOUNT'}</span><h2>{editingAccountId ? 'Update account settings' : 'Create another payment source'}</h2></div>{editingAccountId && <button className="text-button" onClick={() => { setEditingAccountId(null); setAccount(emptyAccount) }}>Cancel</button>}</div>
          <form className="stack-form" onSubmit={submitAccount}>
            <label><span>Account nickname</span><input required value={account.nickname} onChange={(e) => setAccount({ ...account, nickname: e.target.value })} placeholder="Salary, Travel, Wallet…" /></label>
            <label><span>Owner name</span><input required value={account.owner_name} onChange={(e) => setAccount({ ...account, owner_name: e.target.value })} placeholder="Account owner" /></label>
            <label><span>Account type</span><select value={account.account_type} onChange={(e) => setAccount({ ...account, account_type: e.target.value })}><option value="savings">Savings</option><option value="current">Current</option><option value="wallet">Wallet</option></select></label>
            {!editingAccountId && (
              <label>
               <span>Opening balance</span>
              <input
               required
               min="1"
               max="200000"
               step="0.01"
               type="number"
               value={account.opening_balance}
               onChange={(e) =>
                setAccount({
                 ...account,
          opening_balance: e.target.value,
        })
      }
      placeholder="Max ₹2,00,000"
    />
  </label>
)}
            <label><span>Daily payment limit</span><input required min="1" max="200000" step="0.01" type="number" value={account.daily_limit} onChange={(e) => setAccount({ ...account, daily_limit: e.target.value })} placeholder="Max ₹2,00,000" /></label>
            {editingAccountId && <label className="toggle-row"><input type="checkbox" checked={account.is_active !== false} onChange={(e) => setAccount({ ...account, is_active: e.target.checked })} /><span>Account active for payments</span></label>}
            <button className="primary" disabled={busy}>{editingAccountId ? 'Save account changes' : 'Add account'}</button>
          </form>
          <div className="security-note">Opening balance is set once when an account is created. After that, balances change only through payments or <b>account-to-account transfers</b> with matching ledger entries.</div>
        </section>
        <section className="panel">
          <div className="section-title"><div><span className="section-kicker">YOUR ACCOUNTS</span><h2>{accounts.length ? 'Payment sources' : 'No accounts yet'}</h2></div></div>
          <div className="account-manage-list">{accounts.length === 0 ? <div className="empty-state">Create your first account to unlock payments.</div> : accounts.map((item) => {
            const transferTargets = accounts.filter((candidate) => candidate.id !== item.id && candidate.is_active)
            return <div className={`manage-account-card ${item.is_primary ? 'primary-account' : ''}`} key={item.id}>
              <div className="manage-account-top"><div><strong>{item.nickname}</strong><small>{item.account_type} · {item.masked_account}</small></div><span className={`account-state ${item.is_active ? '' : 'paused'}`}>{item.is_primary ? 'PRIMARY' : item.is_active ? 'ACTIVE' : 'PAUSED'}</span></div>
              <div className="manage-balance">{money(item.balance)}</div>
              <div className="manage-account-meta"><span>Daily limit {money(item.daily_limit)}</span><span>{item.owner_name}</span></div>
              <div className="row-actions">
                <button className="secondary" onClick={() => editAccount(item)}>Edit</button>
                {!item.is_primary && item.is_active && <button className="secondary" disabled={busy} onClick={() => actions.setPrimary(item.id)}>Make primary</button>}
                <button className="secondary" disabled={busy || !item.is_active || transferTargets.length === 0} onClick={() => openTransfer(item.id)}>Transfer</button>
              </div>
              {transferSourceId === item.id && <form className="inline-transfer" onSubmit={submitTransfer}>
                <select required value={transferDestinationId} onChange={(e) => setTransferDestinationId(e.target.value)}>
                  <option value="">Transfer to…</option>
                  {transferTargets.map((targetAccount) => <option key={targetAccount.id} value={targetAccount.id}>{targetAccount.nickname} · {targetAccount.masked_account}</option>)}
                </select>
                <input autoFocus required min="0.01" max="200000" step="0.01" type="number" value={transferAmount} onChange={(e) => setTransferAmount(e.target.value)} placeholder="Amount" />
                <button className="primary" disabled={busy}>Transfer money</button>
                <button type="button" className="text-button" onClick={() => { setTransferSourceId(null); setTransferDestinationId(''); setTransferAmount('') }}>Cancel</button>
              </form>}
            </div>
          })}</div>
        </section>
      </div>}

      {section === 'payees' && <div className="manage-grid">
        <section className="panel form-panel"><div className="section-title"><div><span className="section-kicker">{editingTargetId ? 'EDIT PAYEE' : 'ADD PAYEE'}</span><h2>{editingTargetId ? 'Update destination' : 'Create a payment destination'}</h2></div>{editingTargetId && <button className="text-button" onClick={() => { setEditingTargetId(null); setTarget(emptyTarget) }}>Cancel</button>}</div><form className="stack-form" onSubmit={submitTarget}><label><span>Name</span><input required value={target.name} onChange={(e) => setTarget({ ...target, name: e.target.value })} placeholder="Rahul, Phone Recharge, Merchant…" /></label><label><span>Payment type</span><select value={target.kind} onChange={(e) => setTarget({ ...target, kind: e.target.value })}><option value="transfer">Bank transfer</option><option value="upi">UPI</option><option value="mobile_recharge">Mobile recharge</option><option value="merchant_payment">Merchant payment</option><option value="subscription">Subscription</option><option value="donation">Donation</option><option value="other">Other</option></select></label><label><span>Reference</span><input required value={target.reference} onChange={(e) => setTarget({ ...target, reference: e.target.value })} placeholder="UPI / account / mobile / custom ref" /></label><button className="primary" disabled={busy}>{editingTargetId ? 'Save payee' : 'Add payee'}</button></form></section>
        <section className="panel"><div className="section-title"><div><span className="section-kicker">PAYEES</span><h2>Saved destinations</h2></div></div><div className="payee-grid">{targets.length === 0 ? <div className="empty-state">No payees created yet.</div> : targets.map((item) => <div className="payee-card" key={item.id}><div className="payee-avatar">{item.name.slice(0, 2).toUpperCase()}</div><div className="payee-body"><strong>{item.name}</strong><small>{item.kind} · {item.reference}</small><div className="row-actions"><button className="secondary" onClick={() => onTryPrompt(`Pay ₹1,500 to ${item.name}`)}>Pay</button><button className="secondary" onClick={() => editTarget(item)}>Edit</button><button className="danger-link" disabled={busy} onClick={() => actions.deleteTarget(item.name)}>Remove</button></div></div></div>)}</div></section>
      </div>}

      {section === 'bills' && <div className="manage-grid">
        <section className="panel form-panel"><div className="section-title"><div><span className="section-kicker">{editingBillId ? 'EDIT BILL' : 'ADD BILL'}</span><h2>{editingBillId ? 'Update pending bill' : 'Create a payable bill'}</h2></div>{editingBillId && <button className="text-button" onClick={() => { setEditingBillId(null); setBill(emptyBill) }}>Cancel</button>}</div><form className="stack-form" onSubmit={submitBill}><label><span>Provider</span><input required value={bill.provider} onChange={(e) => setBill({ ...bill, provider: e.target.value })} placeholder="Electricity, Broadband…" /></label><label><span>Amount</span><input required min="0.01" max="50000" step="0.01" type="number" value={bill.amount} onChange={(e) => setBill({ ...bill, amount: e.target.value })} placeholder="Bill amount" /></label><label><span>Due date</span><input required type="date" value={bill.due_date} onChange={(e) => setBill({ ...bill, due_date: e.target.value })} /></label><button className="primary" disabled={busy}>{editingBillId ? 'Save bill' : 'Add bill'}</button></form></section>
        <section className="panel"><div className="section-title"><div><span className="section-kicker">BILLS</span><h2>Bill centre</h2></div></div><div className="bill-grid">{bills.length === 0 ? <div className="empty-state">No bills created yet.</div> : bills.map((item) => <div className={`bill-card bill-${item.status.toLowerCase()}`} key={item.id}><div><strong>{item.provider}</strong><small>Due {item.due_date}</small></div><b>{money(item.amount)}</b><span>{item.status}</span><div className="row-actions">{item.status === 'PENDING' && <><button className="secondary" onClick={() => onTryPrompt(`Pay my ${item.provider} bill`)}>Pay</button><button className="secondary" onClick={() => editBill(item)}>Edit</button><button className="danger-link" disabled={busy} onClick={() => actions.deleteBill(item.id)}>Remove</button></>}</div></div>)}</div></section>
      </div>}
    </div>
  )
}
