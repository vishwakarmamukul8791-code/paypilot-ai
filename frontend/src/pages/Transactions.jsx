import { useMemo, useState } from 'react'
import StatusBadge from '../components/StatusBadge'

const money = (v) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 }).format(v || 0)

export default function Transactions({ rows = [], accounts = [] }) {
  const [query, setQuery] = useState('')
  const [accountId, setAccountId] = useState('all')
  const [direction, setDirection] = useState('all')
  const filtered = useMemo(() => rows.filter((t) => {
    const q = query.trim().toLowerCase()
    return (!q || `${t.name} ${t.txn_id} ${t.category} ${t.source_account}`.toLowerCase().includes(q)) && (accountId === 'all' || String(t.account_id) === accountId) && (direction === 'all' || t.direction === direction)
  }), [rows, query, accountId, direction])

  const exportCsv = () => {
    const esc = (v) => `"${String(v ?? '').replaceAll('"', '""')}"`
    const lines = [['Transaction ID', 'Date', 'Account', 'Description', 'Category', 'Direction', 'Amount', 'Risk', 'Status'], ...filtered.map((t) => [t.txn_id, t.created_at, t.source_account, t.name, t.category, t.direction, t.amount, t.risk_score, t.status])]
    const blob = new Blob([lines.map((r) => r.map(esc).join(',')).join('\n')], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = 'paypilot-transactions.csv'; a.click(); URL.revokeObjectURL(url)
  }

  return <section className="panel table-panel"><div className="section-title"><div><span className="section-kicker">ACTIVITY</span><h1>Transaction history</h1><p className="muted">Search, filter and export the ledger created in this isolated session.</p></div><button className="secondary" disabled={!filtered.length} onClick={exportCsv}>Export CSV</button></div><div className="table-tools"><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search transaction or payee" /><select value={accountId} onChange={(e) => setAccountId(e.target.value)}><option value="all">All accounts</option>{accounts.map((a) => <option key={a.id} value={a.id}>{a.nickname}</option>)}</select><select value={direction} onChange={(e) => setDirection(e.target.value)}><option value="all">All activity</option><option value="DEBIT">Payments</option><option value="CREDIT">Money added</option></select></div>{filtered.length === 0 ? <div className="empty-state">No matching transactions.</div> : <div className="table-wrap"><table><thead><tr><th>Transaction</th><th>Account</th><th>Type</th><th>Amount</th><th>Risk</th><th>Status</th></tr></thead><tbody>{filtered.map((t) => <tr key={t.txn_id}><td><strong>{t.name}</strong><small>{t.txn_id}</small></td><td>{t.source_account}</td><td>{t.category}</td><td className={t.direction === 'CREDIT' ? 'positive' : ''}>{t.direction === 'CREDIT' ? '+' : '-'}{money(t.amount)}</td><td>{t.risk_score}/100</td><td><StatusBadge status={t.status} /></td></tr>)}</tbody></table></div>}</section>
}
