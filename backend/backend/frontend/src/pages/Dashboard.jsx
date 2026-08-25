import StatusBadge from '../components/StatusBadge'

const money = (v) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(v || 0)

export default function Dashboard({ data, selectedAccount, onTryPrompt, onManage }) {
  if (!data) return <div className="skeleton">Loading your simulation…</div>
  if (!data.configured) return (
    <section className="welcome-card">
      <div className="welcome-copy">
        <span className="section-kicker">PAYPILOT SANDBOX</span>
        <h1>Build your own financial world.<br />Let the agent operate inside it.</h1>
        <p>Create simulated accounts, payees and bills. PayPilot plans each payment, evaluates risk, requests approval when required, and updates only the state you created.</p>
        <p className="hero-trust-line">No seeded data. No real money. Every decision is traceable.</p>
        <button className="primary" onClick={onManage}>Create your first account</button>
      </div>
      <div className="welcome-visual"><div className="mini-card"><span>Simulation balance</span><strong>₹0</strong><small>No real money connected</small></div><div className="flow-dots"><b>Intent</b><i>→</i><b>Policy</b><i>→</i><b>Approval</b><i>→</i><b>Ledger</b></div></div>
    </section>
  )

  const pendingBill = data.bills.find((b) => b.status === 'PENDING')
  const lastPayment = data.recent_transactions.find((txn) => txn.direction === 'DEBIT')
  const recentTarget = lastPayment
    ? data.beneficiaries.find((target) => target.name.toLowerCase() === lastPayment.name.toLowerCase()) || data.beneficiaries[0]
    : data.beneficiaries[0]
  return (
    <div className="page-stack">
      <section className="dashboard-hero">
        <div className="balance-card">
          <div className="balance-top"><div><span>Selected account</span><strong>{selectedAccount?.nickname || 'Primary account'}</strong></div><span className="card-chip">SIM</span></div>
          <div className="balance-main"><small>Available balance</small><h1>{money(selectedAccount?.balance || 0)}</h1><span>{selectedAccount?.masked_account}</span></div>
          <div className="balance-foot"><div><small>Type</small><b>{selectedAccount?.account_type || 'savings'}</b></div><div><small>Daily limit</small><b>{money(selectedAccount?.daily_limit || 0)}</b></div><div><small>Status</small><b>{selectedAccount?.is_active ? 'Active' : 'Paused'}</b></div></div>
        </div>
        <div className="quick-panel">
          <div><span className="section-kicker">QUICK ACTIONS</span><h2>What do you want to do?</h2></div>
          <div className="quick-grid">
            <button onClick={() => recentTarget ? onTryPrompt(`Pay ₹1,500 to ${recentTarget.name}`) : onManage()}><span>↗</span><b>Send money</b><small>{recentTarget ? `To ${recentTarget.name}` : 'Add a payee first'}</small></button>
            <button onClick={() => pendingBill ? onTryPrompt(`Pay my ${pendingBill.provider} bill`) : onManage()}><span>▤</span><b>Pay a bill</b><small>{pendingBill ? `${pendingBill.provider} · ${money(pendingBill.amount)}` : 'Add a bill first'}</small></button>
            <button onClick={onManage}><span>＋</span><b>Add money</b><small>Simulated account credit</small></button>
            <button onClick={() => onTryPrompt('How much did I spend this month?')}><span>◎</span><b>Spending insight</b><small>Agent-grounded summary</small></button>
          </div>
        </div>
      </section>

      <section className="metric-grid">
        <div className="metric"><span>Total across accounts</span><strong>{money(data.total_balance)}</strong><small>{data.accounts.length} linked simulation account{data.accounts.length === 1 ? '' : 's'}</small></div>
        <div className="metric"><span>Spent this month</span><strong>{money(data.monthly_spending)}</strong><small>All account debits</small></div>
        <div className="metric"><span>Completed activity</span><strong>{data.transaction_count}</strong><small>Credits + payments</small></div>
        <div className="metric"><span>Agent safety</span><strong>Policy-first</strong><small>LLM cannot authorize funds</small></div>
      </section>

      <section className="account-overview panel">
        <div className="section-title"><div><span className="section-kicker">ACCOUNTS</span><h2>Your payment sources</h2></div><button className="secondary" onClick={onManage}>Manage accounts</button></div>
        <div className="account-mini-grid">{data.accounts.map((a) => <div className={`account-mini ${a.id === selectedAccount?.id ? 'selected' : ''}`} key={a.id}><div><strong>{a.nickname}</strong><small>{a.account_type} · {a.masked_account}</small></div><b>{money(a.balance)}</b><span>{a.is_primary ? 'Primary' : a.is_active ? 'Active' : 'Paused'}</span></div>)}</div>
      </section>

      <section className="split-grid">
        <div className="panel"><div className="section-title"><div><span className="section-kicker">RECENT ACTIVITY</span><h2>Latest transactions</h2></div></div><div className="compact-list">{data.recent_transactions.length === 0 ? <div className="empty-inline">No transactions yet.</div> : data.recent_transactions.slice(0, 6).map((t) => <div className="list-row" key={t.txn_id}><div><strong>{t.name}</strong><small>{t.source_account} · {t.category}</small></div><div className="right"><span className={t.direction === 'CREDIT' ? 'positive' : ''}>{t.direction === 'CREDIT' ? '+' : '-'}{money(t.amount)}</span><small>risk {t.risk_score}/100</small></div></div>)}</div></div>
        <div className="panel"><div className="section-title"><div><span className="section-kicker">BILLS</span><h2>Upcoming payments</h2></div></div><div className="compact-list">{data.bills.length === 0 ? <div className="empty-inline">No bills yet.</div> : data.bills.slice(0, 6).map((bill) => <div className="list-row" key={bill.id}><div><strong>{bill.provider}</strong><small>Due {bill.due_date}</small></div><div className="right"><span>{money(bill.amount)}</span><StatusBadge status={bill.status} /></div></div>)}</div></div>
      </section>
    </div>
  )
}
