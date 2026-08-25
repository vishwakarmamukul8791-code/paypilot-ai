# PayPilot cumulative testing fixes 02

This patch is cumulative. It includes all fixes from testing-fixes-01 plus the follow-up safety/usability corrections below.

## 1. High-risk requests now escalate instead of being automatically rejected

- LOW: <= ₹10,000 -> score 20
- MEDIUM: > ₹10,000 and <= ₹50,000 -> score 60
- HIGH: > ₹50,000 -> score 90
- Auto execution remains <= ₹2,000 only.
- Requests above ₹2,000 always require explicit human approval.
- Default hard risk-block threshold is now 95, so a fixed HIGH score of 90 is not rejected only because it is HIGH.
- The ₹1,00,000 per-payment platform cap, account balance, daily limit, account status, destination validation, and execution-time revalidation remain authoritative hard blockers.

Example: with enough balance and daily limit, `Pay ₹60,000 to Rahul` -> HIGH 90/100 -> AWAITING_APPROVAL. The user must explicitly approve before execution.

## 2. Malformed comma amounts are blocked safely

Previously the deterministic parser stripped every comma. That meant an ambiguous input such as `₹19,51` silently became `₹1,951` and could auto-execute.

Now PayPilot accepts clear forms such as:
- ₹19510
- ₹19,510
- ₹1,95,100
- ₹1,951,000

and blocks ambiguous grouping such as:
- ₹19,51
- ₹19,5100

with a message asking for a clear INR amount.

## 3. Fixes retained from patch 01

- Maximum configurable daily account limit: ₹2,00,000.
- Demo per-payment maximum: ₹1,00,000.
- Duplicate payee references are rejected per session + payment type (case-insensitive at the API layer).
- Payee edit cannot steal another payee's saved reference.
- Dashboard Send money quick action prefers the most recently paid destination instead of beneficiaries[0].
- Transaction ordering uses created_at DESC + id DESC for deterministic tie-breaking.

## Existing local data

The patch does not silently delete existing duplicate payees or transactions. Remove/reset existing bad demo data manually if needed; future duplicate creation/edit attempts are blocked.

## Validation

- Full dependency-independent backend suite: PASS.
- Targeted intents, agent flows, and multi-account tests: PASS.
- Runtime dependency import tests require the real LangGraph and Google GenAI packages in the local environment.

## Testing fixes 03 — immutable opening balance + internal transfers

- Opening balance remains a one-time account-creation value.
- Direct post-creation top-ups are disabled (`POST /api/accounts/{id}/funds` returns 410).
- `POST /api/accounts/transfer` moves money between two active accounts in the same demo session.
- Source and destination are database-locked before validation/mutation.
- The transfer writes one DEBIT and one CREDIT ledger row in the same database transaction.
- Retry uses a client-generated idempotency key and does not double-move money.
- Same-account transfers and insufficient-balance transfers are rejected without partial writes.
- Internal transfers do not inflate external-payment monthly-spend metrics.
- Manage UI replaces Add money with Transfer; opening balance remains non-editable.
- Navbar PP spacing and the final hero copy are preserved.
