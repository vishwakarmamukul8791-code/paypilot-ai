import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, ensureSession } from './api/client'
import Dashboard from './pages/Dashboard'
import Assistant from './pages/Assistant'
import Setup from './pages/Setup'
import Transactions from './pages/Transactions'
import Runs from './pages/Runs'
import './styles.css'

const NAV = [['dashboard', 'Home'], ['assistant', 'Pay with AI'], ['setup', 'Manage'], ['transactions', 'Activity'], ['runs', 'Agent trace']]
const ACTIVE_ACCOUNT_KEY = 'paypilot-active-account'

function useTheme() {
  const [theme, setTheme] = useState(() => typeof window === 'undefined' ? 'light' : window.localStorage.getItem('paypilot-theme') || 'light')
  useEffect(() => { document.documentElement.dataset.theme = theme; window.localStorage.setItem('paypilot-theme', theme) }, [theme])
  return [theme, () => setTheme((t) => t === 'dark' ? 'light' : 'dark')]
}

export default function App() {
  const [theme, toggleTheme] = useTheme()
  const [tab, setTab] = useState('dashboard')
  const [dashboard, setDashboard] = useState(null)
  const [transactions, setTransactions] = useState([])
  const [runs, setRuns] = useState([])
  const [activeRun, setActiveRun] = useState(null)
  const [prompt, setPrompt] = useState('')
  const [selectedAccountId, setSelectedAccountId] = useState(() => Number(localStorage.getItem(ACTIVE_ACCOUNT_KEY)) || null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    const [d, t, r] = await Promise.all([api.dashboard(), api.transactions(), api.runs()])
    setDashboard(d); setTransactions(t); setRuns(r)
    return d
  }, [])

  useEffect(() => { ensureSession().then(refresh).catch((e) => setError(e.message)) }, [refresh])
  const effectiveSelectedAccountId = useMemo(() => {
  const accounts = dashboard?.accounts || []

  if (!accounts.length) {
    return null
  }

  const selected = accounts.find(
    (account) =>
      account.id === selectedAccountId &&
      account.is_active,
  )

  if (selected) {
    return selected.id
  }

  const fallback =
    accounts.find(
      (account) =>
        account.is_primary &&
        account.is_active,
    ) ||
    accounts.find((account) => account.is_active) ||
    accounts[0]

  return fallback?.id ?? null
}, [dashboard?.accounts, selectedAccountId])

useEffect(() => {
  if (effectiveSelectedAccountId === null) {
    localStorage.removeItem(ACTIVE_ACCOUNT_KEY)
    return
  }

  localStorage.setItem(
    ACTIVE_ACCOUNT_KEY,
    String(effectiveSelectedAccountId),
  )
}, [effectiveSelectedAccountId])

const selectedAccount = useMemo(
  () =>
    dashboard?.accounts?.find(
      (account) =>
        account.id === effectiveSelectedAccountId,
    ) || null,
  [dashboard?.accounts, effectiveSelectedAccountId],
)

const selectAccount = (id) => {
  setSelectedAccountId(Number(id))
}
  const act = async (fn) => { setBusy(true); setError(''); try { await fn(); await refresh(); return true } catch (e) { setError(e.message); return false } finally { setBusy(false) } }
  const runAgent = async (message) => { setBusy(true); setError(''); try { const result = await api.startAgent(message, effectiveSelectedAccountId); setActiveRun(result); await refresh() } catch (e) { setError(e.message) } finally { setBusy(false) } }
  const decide = async (id, decision) => { setBusy(true); setError(''); try { const result = await api.decide(id, decision); setActiveRun(result); await refresh() } catch (e) { setError(e.message) } finally { setBusy(false) } }
  const reset = async () => { const ok = await act(() => api.reset()); if (ok) { setActiveRun(null); setPrompt(''); setTab('dashboard'); setSelectedAccountId(null); localStorage.removeItem(ACTIVE_ACCOUNT_KEY) } }
  const tryPrompt = (value) => { setPrompt(value); setTab('assistant') }
  const openRun = async (id) => { setBusy(true); setError(''); try { setActiveRun(await api.runDetail(id)); setTab('assistant') } catch (e) { setError(e.message) } finally { setBusy(false) } }

  const actions = {
    createAccount: (p) => act(() => api.createAccount(p)),
    updateAccount: (id, p) => act(() => api.updateAccount(id, p)),
    setPrimary: (id) => act(() => api.setPrimaryAccount(id)),
    transferFunds: (sourceId, destinationId, amount, idempotencyKey) => act(() => api.transferFunds(sourceId, destinationId, amount, idempotencyKey)),
    createTarget: (p) => act(() => api.createTarget(p)),
    updateTarget: (id, p) => act(() => api.updateTarget(id, p)),
    deleteTarget: (name) => act(() => api.deleteTarget(name)),
    createBill: (p) => act(() => api.createBill(p)),
    updateBill: (id, p) => act(() => api.updateBill(id, p)),
    deleteBill: (id) => act(() => api.deleteBill(id)),
  }

  return (
    <div className="app-shell">
      <header className="bank-header">
        <div className="brand-block" onClick={() => setTab('dashboard')} role="button" tabIndex={0}>
          <div className="brand-mark">PP</div>
          <div><strong>PayPilot AI</strong><small>Agentic finance sandbox</small></div>
        </div>
        <div className="header-actions">
          {dashboard?.accounts?.length > 0 && <label className="account-picker"><span>Pay from</span><select
          value={effectiveSelectedAccountId || ''} onChange={(e) => selectAccount(e.target.value)}>{dashboard.accounts.map((a) => <option key={a.id} value={a.id} disabled={!a.is_active}>{a.nickname} · {a.masked_account}{!a.is_active ? ' · Paused' : ''}</option>)}</select></label>}
          <span className="mode-pill">SIMULATION</span>
          <button className="icon-button" onClick={toggleTheme} aria-label="Toggle theme">{theme === 'dark' ? '☀' : '☾'}</button>
          <button className="text-button" disabled={busy} onClick={reset}>Reset</button>
        </div>
      </header>
      <nav className="bank-nav">{NAV.map(([id, label]) => <button key={id} className={tab === id ? 'active' : ''} onClick={() => setTab(id)}>{label}</button>)}</nav>
      <main className="content">
        {error && tab !== 'assistant' && tab !== 'setup' && <div className="error-box global-error">{error}</div>}
        {tab === 'dashboard' && <Dashboard data={dashboard} selectedAccount={selectedAccount} onTryPrompt={tryPrompt} onManage={() => setTab('setup')} />}
        {tab === 'assistant' && <Assistant initialPrompt={prompt} run={activeRun} busy={busy} error={error} onRun={runAgent} onDecision={decide} dashboard={dashboard} selectedAccount={selectedAccount} onSetup={() => setTab('setup')} />}
        {tab === 'setup' && <Setup data={dashboard} busy={busy} error={error} actions={actions} onTryPrompt={tryPrompt} />}
        {tab === 'transactions' && <Transactions rows={transactions} accounts={dashboard?.accounts || []} />}
        {tab === 'runs' && <Runs runs={runs} onOpen={openRun} />}
      </main>
    </div>
  )
}
