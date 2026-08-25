from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.models import AgentEvent


def log_event(
    db: Session,
    run_id: str,
    kind: str,
    title: str,
    detail: dict | None = None,
    *,
    commit: bool = True,
) -> AgentEvent:
    """Append one event with race-free ordering.

    The database-generated primary key is globally monotonic for this table and
    therefore safe to reuse as the timeline ordinal. This avoids the classic
    concurrent `MAX(ordinal) + 1` race without adding a separate sequence column
    to AgentRun or relying on process-local locks.
    """
    event = AgentEvent(
        run_id=run_id,
        ordinal=0,
        kind=kind,
        title=title,
        detail_json=json.dumps(detail or {}, default=str),
    )
    db.add(event)
    db.flush()  # obtains the database-generated primary key inside this transaction
    event.ordinal = int(event.id)
    db.flush()
    if commit:
        db.commit()
        db.refresh(event)
    return event
