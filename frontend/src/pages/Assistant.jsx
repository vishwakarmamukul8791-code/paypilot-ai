import { useMemo, useState } from 'react'
import AgentTimeline from '../components/AgentTimeline'
import StatusBadge from '../components/StatusBadge'

const money = (v) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(v || 0)

export default function Assistant({ initialPrompt, run, busy, error, onRun, onDecision, dashboard, selectedAccount, onSetup }) {
  const [message, setMessage] = useState(initialPrompt || '')
  
  const examples = useMemo(() => {
    const target = dashboard?.beneficiaries?.[0]
    const bill = dashboard?.bills?.find((b) => b.status === 'PENDING')
    const values = []
    if (target) { values.push(`Pay ₹1,500 to ${target.name}`); values.push(`Pay ₹5,000 to ${target.name}`); values.push(`Pay ₹12,000 to ${target.name} only if ₹20,000 remains in my account`) }
    if (bill) values.push(`Pay my ${bill.provider} bill`)
    values.push('How much did I spend this month?')
    return values.slice(0, 5)
  }, [dashboard])
  const submit = () => message.trim() && onRun(message.trim())

  if (!dashboard?.configured) return <section className="panel prompt-panel"><span className="section-kicker">AI PAYMENT</span><h1>Add an account first.</h1><p className="hero-copy">The agent never receives hidden demo money or preloaded payees.</p><button className="primary" onClick={onSetup}>Open Manage</button></section>
  return (
    <div className="assistant-layout">
      <section className="panel prompt-panel">
        <div className="assistant-heading"><div><span className="section-kicker">PAY WITH AI</span><h1>Tell PayPilot what to do.</h1></div><div className="source-pill"><small>Source</small><strong>{selectedAccount?.nickname || 'Select an account'}</strong><span>{money(selectedAccount?.balance || 0)} available</span></div></div>
        <p className="muted">Payments ≤₹2,000 can auto-execute after deterministic checks. Larger payments stop for human approval. Only payees you created can receive simulated funds.</p>
        <textarea value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Example: Pay ₹5,000 to Rahul, but keep at least ₹20,000 in my account" />
        <div className="prompt-actions"><button className="primary" disabled={busy || !message.trim() || !selectedAccount?.is_active} onClick={submit}>{busy ? 'Agent working…' : 'Run payment agent'}</button><span>Natural-language planning · deterministic policy · auditable tools</span></div>
        <div className="examples">{examples.map((x) => <button className="chip" key={x} onClick={() => setMessage(x)}>{x}</button>)}</div>
        {!selectedAccount?.is_active && <div className="info-box">The selected account is paused. Choose an active account from the header or resume it in Manage.</div>}
        {dashboard.beneficiaries.length === 0 && <div className="info-box">No payees exist yet. Add one in Manage before sending money.</div>}
        {error && <div className="error-box">{error}</div>}
      </section>

      {run && <section className="panel result-panel"><div className="section-title"><div><span className="section-kicker">RUN {run.run_id.slice(0, 8)}</span><h2>Agent decision</h2><small className="muted">Source: {run.source_account}</small></div><StatusBadge status={run.status} /></div><div className="summary-box">{run.summary}</div>{run.payment && <div className="payment-card"><div><small>PAYMENT</small><strong>{money(run.payment.amount)} → {run.payment.beneficiary}</strong><span>From {run.payment.source_account}</span></div><div className="risk"><small>RISK</small><strong>{run.payment.risk_level} · {run.payment.risk_score}/100</strong></div>{run.payment.risk_reasons?.length > 0 && <ul>{run.payment.risk_reasons.map((r) => <li key={r}>{r}</li>)}</ul>}{(run.payment.conditions?.minimum_remaining_balance != null || run.payment.conditions?.confirm_if_above != null) && <ul className="conditions-list">{run.payment.conditions.minimum_remaining_balance != null && <li>Keep at least {money(run.payment.conditions.minimum_remaining_balance)} remaining</li>}{run.payment.conditions.confirm_if_above != null && <li>Require confirmation above {money(run.payment.conditions.confirm_if_above)}</li>}</ul>}{run.status === 'AWAITING_APPROVAL' && <div className="approval-actions"><button className="primary" disabled={busy} onClick={() => onDecision(run.run_id, 'approve')}>Approve payment</button><button className="danger" disabled={busy} onClick={() => onDecision(run.run_id, 'reject')}>Reject</button></div>}</div>}</section>}

      <section className="panel timeline-panel"><div className="section-title"><div><span className="section-kicker">AGENT TRACE</span><h2>What happened under the hood</h2></div><span className="muted">Intent → tools → risk → policy → approval → ledger</span></div><AgentTimeline events={run?.events || []} /></section>
    </div>
  )
}
