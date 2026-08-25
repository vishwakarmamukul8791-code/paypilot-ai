import StatusBadge from '../components/StatusBadge'

export default function Runs({ runs = [], onOpen }) {
  return <section className="panel table-panel"><div className="section-title"><div><span className="section-kicker">AGENT TRACE</span><h1>Run history</h1><p className="muted">Open any run to inspect intent, tools, policy, approval and execution events.</p></div></div>{runs.length === 0 ? <div className="empty-state">No agent runs yet.</div> : <div className="run-list">{runs.map((run) => <button className="run-row" key={run.run_id} onClick={() => onOpen(run.run_id)}><div><strong>{run.user_request}</strong><small>{run.source_account} · {run.summary || 'Processing'}</small></div><StatusBadge status={run.status} /></button>)}</div>}</section>
}
