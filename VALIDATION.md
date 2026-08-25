# Validation record — 22 August 2026

This artifact was reviewed as a portfolio-grade **fake-money simulation**. “Bug-free” cannot be proven for any non-trivial system, so this document records what was actually checked and what still depends on the deployment environment.

## Security/correctness fixes applied in this hardening pass

- Removed release leakage/bloat: local `.env`, SQLite DB/WAL, bundled virtualenv and `node_modules` are not shipped.
- Side-effect gate: LLM-only interpretation cannot manufacture transfer/bill-payment authority.
- Server-issued session UUIDs are mandatory on stateful routes; forged/expired sessions are rejected.
- Added session-creation and global agent capacity limits in addition to per-session limits.
- Final payment path revalidates state under process + database serialization.
- Ledger debit, transaction row, payment state and final audit events use one database commit boundary.
- Idempotent payment execution remains enforced by unique keys.
- Reset/TTL cleanup also purges associated workflow checkpoints where available.
- Hosted deployment is configured for managed PostgreSQL domain state rather than ephemeral container SQLite.
- Added readiness, DB health, request IDs/timing, no-store API caching and security headers.
- Docker backend runs as non-root; Docker/release ignores exclude secrets/runtime state.
- Input whitespace/shape validation strengthened.
- Added multi-account source isolation, editable account metadata, primary selection, pause/resume, and ledgered add-money credits.
- Added editable payees/pending bills, transaction search/filter/export UI, and explicit source-account selection for agent runs.
- Replaced the earlier portfolio-like layout with a distinct payment-dashboard UI and blue/indigo fintech visual system.
- Added a partial unique database index so a session cannot persist two primary accounts.
- Updated current model default to `gemini-3.7-flash` and corrected dependency lower bounds to published releases (`langgraph>=1.2.10`, `google-genai>=2.17.0`).

## Local validation performed

The final pass ran:

```bash
cd backend
python -m compileall -q app tests
pytest -q --ignore=tests/test_runtime_dependencies.py
```

Result: **89/89 dependency-independent backend tests passed** after the multi-account/payment-site feature pass.

The complete suite contains **91 tests**. The remaining two tests intentionally instantiate the real LangGraph SQLite runtime and verify the installed Google GenAI SDK exposes the Interactions client. In this sandbox those two checks fail only because `langgraph` and `google-genai` are not installed and package download is unavailable here; they are retained in the repository so clean-install CI/deployment must prove them rather than silently skipping them.

A public API smoke test was also run against the extracted release. It passed session isolation, empty-session setup, user-created targets, `₹499` auto execution, `₹12,000` human approval/resume, negated-payment blocking, reset and post-reset emptiness. Because LangGraph is not installed in this sandbox, that smoke run correctly reported the documented deterministic fallback runtime; deployment acceptance still requires `/health` to report `agent_runtime=langgraph` after clean dependencies are installed.

The final packaging pass also checks:

- frontend JSX parsing with the TypeScript parser and CSS parsing with PostCSS, package/lock consistency, and JSON/YAML configuration parseability locally; a clean Vite production build remains an explicit CI/local acceptance check when npm dependencies are available;
- release ZIP contains no `.env`, local databases/WAL, virtualenv, `node_modules`, caches, build output or Git metadata;
- no obvious API-key/token patterns are present in the release source;
- public smoke flow against the locally available dependency set when the API can start.

## Deployment acceptance criteria

A production-like public demo is accepted only when:

1. `/ready` returns 200 and `database=ok`.
2. `/health` reports `agent_runtime=langgraph` for the full orchestration path.
3. CI backend tests and frontend production build are green from clean installs.
4. Render uses managed PostgreSQL and Vercel/Render origins are configured exactly.
5. A fresh recruiter session passes the documented auto-execute, HITL, guardrail, reset and isolation smoke flow.
