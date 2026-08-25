# PayPilot AI — Interview Guide

## 30-second pitch

“PayPilot AI is a fake-money agentic payment orchestrator. Natural language is converted into a typed intent, LangGraph coordinates narrow tools, but the LLM never owns payment authority. Deterministic policy and risk decide whether a request is blocked, auto-authorized up to ₹2,000, or paused for human approval. Before any ledger mutation I acquire a DB-side serialization lock, re-read balance/limits/bill state, and execute idempotently in one transaction. The UI exposes the full trace, so I can explain exactly what the model did versus what trusted code authorized.”

## Architecture questions you should be ready for

**Why not let the LLM decide approval?**  
LLMs are probabilistic and prompt-injectable. They can interpret language, but deterministic application policy owns side-effect authority. In this project an LLM-only result cannot create a transfer if deterministic parsing did not recognize one.

**Why LangGraph?**  
The workflow has explicit state, branching and a human-interrupt/resume point. It is useful because approval is a real state transition rather than a chat convention. Domain payment state remains authoritative even if a checkpoint is unavailable.

**Risk vs approval?**  
They are separate. A ₹5,000 request is LOW risk under the transparent amount bands but still requires approval because the auto-execution ceiling is ₹2,000.

**How do you prevent double payment?**  
Each payment request has an idempotency key; the transaction table enforces uniqueness. Execution checks for an existing transaction and returns it instead of debiting again.

**What if two payments run at once?**  
The final authorization path uses a per-session process lock plus database serialization (`BEGIN IMMEDIATE` for SQLite, row lock for PostgreSQL), then recalculates balance and daily spend before mutation.

**What if the server crashes after approval?**  
Approval is not permanent execution authority. The durable payment request remains `AWAITING_APPROVAL`, and every resume revalidates current state. The actual ledger debit, transaction row and final audit status share one commit boundary.

**What is observable?**  
Intent/parser source, plan, each tool call/result, risk, policy checks, approval, authorization, execution, final transaction and request latency/request ID. Prompts are not copied into request logs.

**Why fixed risk rather than ML fraud scoring?**  
The portfolio focuses on agent safety/orchestration. Pretending a tiny fake dataset is a fraud model would weaken the project. Fixed bands are measurable, testable and honest; a real system would call an independently governed risk service/model.

**What changes for real production banking?**  
Real authN/authZ, KYC/AML, fraud systems, payment rails, distributed locks/idempotency, reconciliation, secrets/KMS/HSM, encryption and PII controls, immutable audit retention, backups/DR, migrations, SLOs and regulated operations.

## Strong engineering signals in this repo

- typed intent/state/tool boundaries;
- deterministic side-effect gate around probabilistic AI;
- explicit HITL state machine;
- execution-time revalidation against stale approvals;
- transactional/idempotent ledger mutation;
- concurrency controls across threads/processes/DB workers;
- durable-vs-ephemeral state separation;
- session isolation and public-demo abuse controls;
- structured observability and health/readiness;
- unit/API/concurrency/security/dependency tests;
- clean Docker/CI/deployment/release packaging.

## Demo sequence for an interviewer

1. Create an account with enough balance and a daily limit above ₹60,000 (for example ₹1,00,000).
2. Add `My Mobile` and `My Merchant` yourself.
3. `Recharge My Mobile for ₹499` -> LOW risk + auto execution.
4. `Pay ₹12,000 to My Merchant` -> MEDIUM risk + human approval.
5. Approve -> latest-state revalidation -> one transaction.
6. `Do not pay ₹500 to My Merchant` -> deterministic guardrail, no transaction.
7. Open the trace and point to the model/deterministic/tool/approval/execution boundaries.

## Multi-account / product-depth talking points

**How do multiple accounts avoid cross-account debits?**  
The selected source account is persisted on `AgentRun`, copied into `PaymentRequest`, and then onto every `Transaction`. Daily-limit checks, balance reads, row locking, execution and spending analysis all use that same `account_id`. The frontend selection is therefore not just presentation state.

**Why can account metadata be edited but not the balance field directly?**  
A hidden balance edit would destroy ledger integrity. PayPilot lets the user change nickname, type, daily limit and active/paused state, while balance changes happen through explicit `add_money` credits or payment debits so the transaction history still reconciles.

**What standard payment-product behavior is represented?**  
Multiple funding accounts, primary/default account selection, pause/resume, add-money credits, saved payees, bill management, source-account selection, transaction search/filter/export and explicit payment approval. These are simulated product features layered around the agent rather than replacing the core agentic workflow.
