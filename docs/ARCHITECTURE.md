# Architecture

PayPilot AI separates **language understanding** from **financial authority**.

```text
Browser
  -> FastAPI session boundary
  -> selected source account + Agent run + audit record
  -> deterministic parser + optional Gemini structured extraction
  -> LangGraph plan/orchestration
  -> allow-listed tools
  -> deterministic risk + policy engine
  -> auto authorization (<= ₹2,000) OR human approval (> ₹2,000)
  -> database-serialized latest-state revalidation
  -> idempotent simulated ledger transaction
  -> atomic commit + observable agent trace
```

## Authority boundary

The LLM may help understand a user's wording, but it cannot manufacture payment authority. For a side-effecting `transfer` or `pay_bill`, deterministic parsing must first recognize a supported immediate financial action. Amount, target/provider, currency and confirmation conditions that can affect authorization stay under deterministic validation. LLM-only interpretation is limited to read-only analysis intents.

This deliberately avoids the dangerous pattern `LLM output -> payment API`.

## State

Two types of state are intentionally separate:

1. **Domain state** — sessions, accounts, destinations, bills, payment requests, transactions, agent runs and audit events. This is the source of truth for money and authorization.
2. **Workflow checkpoint state** — LangGraph checkpoints used to pause/resume a run.

A pending approval is persisted in the domain database. If a lightweight graph checkpoint is unavailable after a process restart, approval can safely resume from the durable payment request and still passes the same execution-time revalidation/idempotency boundary.

## Persistence

Local Docker uses SQLite files on the `paypilot_data` named volume. Hosted deployment should set `DATABASE_URL` to managed PostgreSQL; the configuration normalizes common `postgres://` / `postgresql://` URLs to SQLAlchemy's psycopg driver.

SQLite enables foreign keys, WAL, `synchronous=FULL`, a busy timeout and a 15-second connection timeout. PostgreSQL is preferred for hosted durability/concurrency.

## Concurrency and atomicity

The final check/execute path uses two levels of serialization:

- a per-session in-process lock;
- a database lock: `BEGIN IMMEDIATE` on SQLite or `SELECT ... FOR UPDATE` on the **selected source-account row** for databases such as PostgreSQL.

Inside that boundary PayPilot re-reads the destination/bill, risk, balance, daily spend and user conditions. Authorization, ledger debit, transaction row, bill state, payment state and final audit events are committed together. An idempotency key prevents a retry from creating a second transaction.

## Session isolation

`POST /api/demo/session` is the only route that creates a session. Stateful routes require the exact server-issued UUID in `X-Demo-Session`; malformed, missing, unknown or expired identifiers are rejected. Every domain query is scoped by session ID.

This UUID is a public-demo capability, **not production authentication**.

## Observability

The UI exposes per-run agent events (intent, plan, tool calls/results, policy, approval, authorization, execution and final status). The API adds `X-Request-ID` and `X-Process-Time-Ms` and writes structured request metadata without logging user prompts. `/health` reports runtime/dependency state and `/ready` verifies DB availability.

## Deployment topology

```text
Vercel static React SPA
       |
       v
Render FastAPI container (non-root)
       |
       +--> managed PostgreSQL  <- durable domain state
       |
       +--> Gemini API (optional intent augmentation)
       |
       `--> local lightweight LangGraph checkpoint DB
```

The product remains fully explorable without a Gemini API key because deterministic intent parsing is the safe fallback.

## Multi-account payment state

A session may own multiple simulated Savings, Current and Wallet accounts. One account is primary for convenience, while the frontend may explicitly select any active account as the source for an agent run. `AgentRun`, `PaymentRequest` and `Transaction` persist `account_id`, so authorization, daily limits, debit execution, audit presentation and spending analysis cannot silently drift to another account.

Account metadata (nickname, type, daily limit, active/paused state) is editable, but balances are intentionally not directly editable after account creation. The opening balance is established once when an account is created. After that, balance movement occurs through simulated payments or atomic account-to-account transfers. Internal transfers lock both participating accounts in stable ID order and create matching DEBIT and CREDIT ledger entries inside one database transaction.
