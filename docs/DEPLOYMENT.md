# Deployment

## 1. Local reproducible demo

```bash
cp .env.example .env
docker compose up --build
```

Docker Compose persists both SQLite domain state and LangGraph checkpoint state in the `paypilot_data` named volume. Use `docker compose down -v` only when you intentionally want to delete local demo state.

## 2. Render backend

The included `render.yaml` intentionally leaves two environment values for you to provide:

- `DATABASE_URL` — **managed PostgreSQL**, not a local Render filesystem SQLite file.
- `CORS_ORIGINS` — the exact deployed frontend origin, e.g. `https://your-paypilot.vercel.app`.

Optional: `GEMINI_API_KEY`. The deterministic parser remains functional without it.

Why PostgreSQL: free/container filesystems can be replaced on restart/redeploy. Payment/domain state is the durable source of truth and must not depend on an ephemeral container disk. The lightweight LangGraph SQLite checkpoint is allowed to be ephemeral because a persisted pending approval can recover through the durable domain state and is revalidated before execution.

Verify after deployment:

```text
GET /ready  -> 200, database=ok
GET /health -> agent_runtime=langgraph for the full graph runtime
```

A `degraded` health status is intentionally visible if the DB is unavailable or LangGraph fell back.

## 3. Vercel frontend

- Root: `frontend`
- Build: `npm run build`
- Output: `dist`
- Env: `VITE_API_BASE_URL=https://YOUR-RENDER-BACKEND`

The frontend session client automatically replaces an expired/missing demo session once and retries the request.

## 4. Recruiter smoke test

Use an incognito window and verify:

1. Fresh session starts empty.
2. Create an account and your own destination.
3. <= ₹2,000 completes after deterministic checks without human approval.
4. > ₹2,000 pauses at `AWAITING_APPROVAL`, then completes only after approval.
5. A negated/scheduled/multi-action instruction is blocked and creates no transaction.
6. Reset returns the session to empty.
7. A second browser profile has independent state.
8. Restart/redeploy the backend with managed PostgreSQL and confirm domain state remains available until TTL/reset.

Automated API smoke test:

```bash
python scripts/smoke_test.py https://YOUR-RENDER-BACKEND
```
