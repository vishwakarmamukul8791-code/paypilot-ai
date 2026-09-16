import test from 'node:test'
import assert from 'node:assert/strict'
import { api } from '../src/api/client.js'

const storage = new Map()
globalThis.localStorage = {
  getItem: (key) => storage.get(key) ?? null,
  setItem: (key, value) => storage.set(key, String(value)),
  removeItem: (key) => storage.delete(key),
}
const response = (status, data) => ({ ok: status < 400, status, json: async () => data })

test('uncertain payment outcome retains operation ID across retries', async () => {
  storage.clear()
  storage.set('paypilot_demo_session', 'session-one')
  const bodies = []
  globalThis.fetch = async (_url, options) => {
    bodies.push(JSON.parse(options.body))
    if (bodies.length === 1) throw new TypeError('Connection lost after submission')
    return response(200, { run_id: 'same-run', status: 'COMPLETED' })
  }
  await assert.rejects(api.startAgent('Pay ₹100 to Rahul', 1))
  await assert.rejects(api.startAgent('Pay ₹200 to Rahul', 1), /previous payment/)
  await api.startAgent('Pay ₹100 to Rahul', 1)
  assert.equal(bodies[0].operation_id, bodies[1].operation_id)
  await api.startAgent('Pay ₹100 to Rahul', 1)
  assert.notEqual(bodies[1].operation_id, bodies[2].operation_id)
})

test('expired session does not silently replay a payment in a new session', async () => {
  storage.clear()
  storage.set('paypilot_demo_session', 'expired-session')
  let requests = 0
  globalThis.fetch = async () => {
    requests += 1
    return response(404, { detail: 'Simulation session expired or does not exist.' })
  }
  await assert.rejects(api.startAgent('Pay ₹100 to Rahul', 1), /expired/)
  assert.equal(requests, 1)
  assert.equal(localStorage.getItem('paypilot_demo_session'), null)
})

test('definite validation rejection releases the pending operation', async () => {
  storage.clear()
  storage.set('paypilot_demo_session', 'session-one')
  globalThis.fetch = async () => response(422, { detail: 'Invalid request' })
  await assert.rejects(api.startAgent('Pay ₹100 to Rahul', 1))
  assert.equal(localStorage.getItem('paypilot_pending_operation'), null)
})
