# Validation Record — 25 August 2026

PayPilot AI was validated as a fake-money agentic payment orchestration simulation.

## Clean-install CI validation

GitHub Actions validates the project from clean environments using Python 3.12 and Node.js 22.

### Backend

```bash
pip install -r backend/requirements-dev.txt
pip check
python -m compileall -q app tests
pytest -q
```

Result:

- dependency installation: PASS
- dependency consistency (`pip check`): PASS
- Python compilation: PASS
- complete backend test suite: PASS
- LangGraph runtime dependency checks: PASS
- Google GenAI dependency checks: PASS

### Frontend

```bash
npm ci
npm run lint
npm run build
```

Result:

- clean npm install: PASS
- ESLint: PASS
- Vite production build: PASS

## Validated behavior

The automated suite covers:

- empty recruiter/demo sessions
- server-issued session isolation
- multiple simulated accounts
- maximum opening balance of ₹2,00,000
- maximum configurable daily payment limit of ₹2,00,000
- account pause/resume and primary selection
- source-account isolation
- atomic account-to-account transfers
- paired DEBIT/CREDIT ledger entries
- transfer idempotency and rollback
- payment destination management
- duplicate destination-reference protection
- bill management and bill integrity
- deterministic payment intent parsing
- malformed INR amount rejection
- LOW / MEDIUM / HIGH risk boundaries
- payments up to ₹2,000 auto-authorizing after checks
- payments above ₹2,000 requiring human approval
- HIGH-risk requests escalating to approval when otherwise eligible
- ₹1,00,000 per-payment platform limit
- execution-time state revalidation
- stale approval protection
- insufficient-balance protection
- daily-limit enforcement
- Decimal/fixed-point money handling
- payment idempotency
- concurrent execution protection
- reset and TTL cleanup
- rate limiting
- LangGraph workflow initialization

## Validation boundary

This validation applies to the **fake-money portfolio simulation only**.

PayPilot AI is not certified or intended for real banking, real payment processing, real financial credentials, or regulated production use.