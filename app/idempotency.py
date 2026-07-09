import hashlib
import json
from typing import Optional, Tuple, Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models import IdempotencyRecord


def _hash_body(body: dict) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def get_cached_response(
    db: Session, workspace_id: str, endpoint: str, idempotency_key: str, body: dict
) -> Optional[Tuple[int, Any]]:
    """Return (status_code, body) if this exact request was already handled.

    Raises 409 if the same idempotency key is reused with a different body.
    """
    existing = (
        db.query(IdempotencyRecord)
        .filter(
            IdempotencyRecord.workspace_id == workspace_id,
            IdempotencyRecord.endpoint == endpoint,
            IdempotencyRecord.idempotency_key == idempotency_key,
        )
        .first()
    )
    if existing is None:
        return None

    if existing.request_hash != _hash_body(body):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency-Key was already used with a different request body",
        )
    return existing.response_status_code, existing.response_body


def store_response(
    db: Session,
    workspace_id: str,
    endpoint: str,
    idempotency_key: str,
    body: dict,
    status_code: int,
    response_body: Any,
) -> None:
    record = IdempotencyRecord(
        workspace_id=workspace_id,
        endpoint=endpoint,
        idempotency_key=idempotency_key,
        request_hash=_hash_body(body),
        response_status_code=status_code,
        response_body=response_body,
    )
    db.add(record)
    try:
        db.flush()
    except IntegrityError:
        # Lost a race with a concurrent identical request; that's fine, the
        # other request's stored response is the source of truth.
        db.rollback()