const API_BASE = (
  import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
).replace(/\/$/, '')

const SESSION_KEY = 'paypilot_demo_session'
const REQUEST_TIMEOUT_MS = 30000

let sessionPromise = null

function clearSession(expectedSessionId = null) {
  const current = localStorage.getItem(SESSION_KEY)

  if (!expectedSessionId || current === expectedSessionId) {
    localStorage.removeItem(SESSION_KEY)
  }
}

async function createSession() {
  const controller = new AbortController()
  const timer = setTimeout(
    () => controller.abort(),
    REQUEST_TIMEOUT_MS,
  )

  let response

  try {
    response = await fetch(
      `${API_BASE}/api/demo/session`,
      {
        method: 'POST',
        signal: controller.signal,
      },
    )
  } catch (error) {
    if (error?.name === 'AbortError') {
      throw new Error(
        'The backend took too long to respond. Please try again.',
        { cause: error },
      )
    }

    throw new Error(
      'Could not reach the PayPilot API. Check the backend and try again.',
      { cause: error },
    )
  } finally {
    clearTimeout(timer)
  }

  const data = await response.json().catch(() => ({}))

  if (!response.ok) {
    throw new Error(
      data.detail || 'Could not create simulation session',
    )
  }

  if (
    typeof data.session_id !== 'string' ||
    !data.session_id
  ) {
    throw new Error(
      'The backend returned an invalid demo session.',
    )
  }

  localStorage.setItem(
    SESSION_KEY,
    data.session_id,
  )

  return data.session_id
}

export async function ensureSession() {
  const existing = localStorage.getItem(SESSION_KEY)

  if (existing) {
    return existing
  }

  if (!sessionPromise) {
    sessionPromise = createSession().finally(() => {
      sessionPromise = null
    })
  }

  return sessionPromise
}

function errorMessage(data, status) {
  if (typeof data?.detail === 'string') {
    return data.detail
  }

  if (Array.isArray(data?.detail)) {
    return data.detail
      .map((item) => item.msg || 'Invalid input')
      .join('; ')
  }

  return `Request failed (${status})`
}

async function performRequest(
  path,
  options,
  sessionId,
) {
  const controller = new AbortController()
  const timer = setTimeout(
    () => controller.abort(),
    REQUEST_TIMEOUT_MS,
  )

  try {
    return await fetch(
      `${API_BASE}${path}`,
      {
        ...options,
        signal: controller.signal,
        headers: {
          'Content-Type': 'application/json',
          'X-Demo-Session': sessionId,
          ...(options.headers || {}),
        },
      },
    )
  } finally {
    clearTimeout(timer)
  }
}

async function request(
  path,
  options = {},
  retrySession = true,
) {
  const sessionId = await ensureSession()

  let response

  try {
    response = await performRequest(
      path,
      options,
      sessionId,
    )
  } catch (error) {
    if (error?.name === 'AbortError') {
      throw new Error(
        'The backend took too long to respond. Please try again.',
        { cause: error },
      )
    }

    throw new Error(
      'Could not reach the PayPilot API. Check the backend and try again.',
      { cause: error },
    )
  }

  const data = await response
    .json()
    .catch(() => ({}))

  if (
    response.status === 404 &&
    retrySession &&
    typeof data?.detail === 'string' &&
    data.detail.includes('Simulation session')
  ) {
    clearSession(sessionId)

    return request(
      path,
      options,
      false,
    )
  }

  if (!response.ok) {
    throw new Error(
      errorMessage(data, response.status),
    )
  }

  return data
}

export const api = {
  dashboard: () =>
    request('/api/dashboard'),

  transactions: () =>
    request('/api/transactions'),

  runs: () =>
    request('/api/agent/runs'),

  runDetail: (id) =>
    request(`/api/agent/runs/${id}`),

  startAgent: (
    message,
    sourceAccountId,
  ) =>
    request(
      '/api/agent/run',
      {
        method: 'POST',
        body: JSON.stringify({
          message,
          source_account_id:
            sourceAccountId || null,
        }),
      },
    ),

  decide: (
    id,
    decision,
  ) =>
    request(
      `/api/agent/runs/${id}/decision`,
      {
        method: 'POST',
        body: JSON.stringify({
          decision,
        }),
      },
    ),

  createAccount: (payload) =>
    request(
      '/api/accounts',
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
    ),

  updateAccount: (
    id,
    payload,
  ) =>
    request(
      `/api/accounts/${id}`,
      {
        method: 'PATCH',
        body: JSON.stringify(payload),
      },
    ),

  setPrimaryAccount: (id) =>
    request(
      `/api/accounts/${id}/primary`,
      {
        method: 'POST',
      },
    ),

  transferFunds: (
    sourceAccountId,
    destinationAccountId,
    amount,
    idempotencyKey,
  ) =>
    request(
      '/api/accounts/transfer',
      {
        method: 'POST',
        body: JSON.stringify({
          source_account_id:
            sourceAccountId,
          destination_account_id:
            destinationAccountId,
          amount,
          idempotency_key:
            idempotencyKey,
        }),
      },
    ),

  createTarget: (payload) =>
    request(
      '/api/targets',
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
    ),

  updateTarget: (
    id,
    payload,
  ) =>
    request(
      `/api/targets/${id}`,
      {
        method: 'PATCH',
        body: JSON.stringify(payload),
      },
    ),

  deleteTarget: (name) =>
    request(
      `/api/targets/${encodeURIComponent(name)}`,
      {
        method: 'DELETE',
      },
    ),

  createBill: (payload) =>
    request(
      '/api/bills',
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
    ),

  updateBill: (
    id,
    payload,
  ) =>
    request(
      `/api/bills/${id}`,
      {
        method: 'PATCH',
        body: JSON.stringify(payload),
      },
    ),

  deleteBill: (id) =>
    request(
      `/api/bills/${id}`,
      {
        method: 'DELETE',
      },
    ),

  reset: () =>
    request(
      '/api/demo/reset',
      {
        method: 'POST',
      },
    ),
}