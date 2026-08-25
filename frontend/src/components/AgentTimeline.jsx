function pretty(value) {
  if (value === null || value === undefined) return ''
  if (typeof value === 'string') return value
  return JSON.stringify(value, null, 2)
}

export default function AgentTimeline({ events = [] }) {
  if (!events.length) return <div className="empty-state">Run a prompt to see the agent's decisions and tool calls.</div>
  return (
    <div className="timeline">
      {events.map((event, index) => (
        <div className="timeline-row" key={`${event.ordinal}-${event.title}`}>
          <div className="timeline-rail"><span>{index + 1}</span></div>
          <div className="timeline-card">
            <div className="timeline-top"><strong>{event.title}</strong><code>{event.kind}</code></div>
            {Object.keys(event.detail || {}).length > 0 && <pre>{pretty(event.detail)}</pre>}
          </div>
        </div>
      ))}
    </div>
  )
}
