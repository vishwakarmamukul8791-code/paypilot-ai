from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]


def _positive_int(name: str, default: str) -> int:
    raw = os.getenv(name, default)
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value < 1:
        raise RuntimeError(f"{name} must be >= 1")
    return value


def _money(name: str, default: str) -> Decimal:
    raw = os.getenv(name, default)
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise RuntimeError(f"{name} must be a valid decimal amount") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be > 0")
    return value.quantize(Decimal("0.01"))


def _database_url() -> str:
    raw = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'paypilot.db'}")
    if raw.startswith("postgres://"):
        return "postgresql+psycopg://" + raw[len("postgres://"):]
    if raw.startswith("postgresql://"):
        return "postgresql+psycopg://" + raw[len("postgresql://"):]
    return raw


@dataclass(frozen=True)
class Settings:
    app_name: str = "PayPilot AI"
    environment: str = os.getenv("ENVIRONMENT", "demo")
    database_url: str = _database_url()
    langgraph_db_path: str = os.getenv("LANGGRAPH_DB_PATH", str(BASE_DIR / "langgraph.db"))
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY") or None
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.7-flash")
    cors_origins: str = os.getenv("CORS_ORIGINS", "http://localhost:5173")
    demo_session_ttl_hours: int = _positive_int("DEMO_SESSION_TTL_HOURS", "24")
    max_transfer_amount: Decimal = _money("MAX_TRANSFER_AMOUNT", "100000")
    auto_execute_threshold: Decimal = _money("AUTO_EXECUTE_THRESHOLD", "2000")
    high_risk_block_score: int = _positive_int("HIGH_RISK_BLOCK_SCORE", "95")
    agent_runs_per_minute: int = _positive_int("AGENT_RUNS_PER_MINUTE", "12")
    global_agent_runs_per_minute: int = _positive_int("GLOBAL_AGENT_RUNS_PER_MINUTE", "120")
    session_creates_per_minute: int = _positive_int("SESSION_CREATES_PER_MINUTE", "60")

    def __post_init__(self) -> None:
        if self.auto_execute_threshold > self.max_transfer_amount:
            raise RuntimeError("AUTO_EXECUTE_THRESHOLD cannot exceed MAX_TRANSFER_AMOUNT")
        if self.high_risk_block_score > 100:
            raise RuntimeError("HIGH_RISK_BLOCK_SCORE cannot exceed 100")

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]


settings = Settings()
