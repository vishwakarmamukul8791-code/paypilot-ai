from __future__ import annotations

import json
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.agents import runtime
from app.api.routes import router
from app.core.config import settings
from app.database.db import Base, SessionLocal, engine

logger = logging.getLogger("paypilot.api")
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="PayPilot AI API",
    version="2.0.0",
    description=(
        "Public-simulation-first multi-account agentic payment orchestration API with "
        "user-created session state and no real-money integration."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Demo-Session"],
)


@app.middleware("http")
async def security_and_observability(request: Request, call_next):
    request_id = uuid.uuid4().hex
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.exception(
            json.dumps(
                {
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": 500,
                    "duration_ms": duration_ms,
                }
            )
        )
        raise

    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time-Ms"] = str(duration_ms)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"

    logger.info(
        json.dumps(
            {
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
            }
        )
    )
    return response


app.include_router(router)


def _runtime_info() -> dict:
    return {
        "agent_runtime": runtime.mode,
        "runtime_fallback_reason": getattr(runtime, "reason", None),
        "gemini_configured": bool(settings.gemini_api_key),
    }


def _database_ok() -> bool:
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@app.get("/")
def root():
    return {
        "name": "PayPilot AI",
        "status": "ok",
        "demo": True,
        "version": "2.0.0",
        **_runtime_info(),
    }


@app.get("/health")
def health():
    database_ok = _database_ok()
    degraded = not database_ok or runtime.mode != "langgraph"
    return {
        "status": "degraded" if degraded else "healthy",
        "environment": settings.environment,
        "database": "ok" if database_ok else "unavailable",
        "real_money": False,
        **_runtime_info(),
    }


@app.get("/ready")
def ready():
    database_ok = _database_ok()
    payload = {
        "status": "ready" if database_ok else "not_ready",
        "database": "ok" if database_ok else "unavailable",
        "real_money": False,
        **_runtime_info(),
    }
    return JSONResponse(payload, status_code=200 if database_ok else 503)
