const LABELS = {
  AWAITING_APPROVAL: 'Awaiting approval', COMPLETED: 'Completed', BLOCKED: 'Blocked',
  REJECTED: 'Rejected', RUNNING: 'Running', FAILED: 'Failed', PENDING: 'Pending', PAID: 'Paid',
}

export default function StatusBadge({ status }) {
  return <span className={`badge badge-${String(status).toLowerCase()}`}>{LABELS[status] || status}</span>
}
