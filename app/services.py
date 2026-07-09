from datetime import datetime
from typing import Optional, List, Tuple

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import (
    ApprovalRequest,
    ApprovalStatus,
    AuditLog,
    OutboxEvent,
    FINAL_STATUSES,
)
from app.schemas import ApprovalRequestCreate


def _write_audit(
    db: Session,
    *,
    workspace_id: str,
    approval_request_id: str,
    actor_user_id: str,
    action: str,
    from_status: Optional[str],
    to_status: Optional[str],
    details: Optional[dict] = None,
) -> None:
    db.add(
        AuditLog(
            workspace_id=workspace_id,
            approval_request_id=approval_request_id,
            actor_user_id=actor_user_id,
            action=action,
            from_status=from_status,
            to_status=to_status,
            details=details,
        )
    )


def _write_outbox(
    db: Session,
    *,
    workspace_id: str,
    approval_request_id: str,
    event_type: str,
    payload: dict,
) -> None:
    db.add(
        OutboxEvent(
            workspace_id=workspace_id,
            aggregate_id=approval_request_id,
            event_type=event_type,
            payload=payload,
        )
    )


def _event_payload(req: ApprovalRequest) -> dict:
    # Sanitized: only ids and status - no free-text fields that a caller
    # might (against validation) have tried to stuff secrets into.
    return {
        "approvalRequestId": req.id,
        "workspaceId": req.workspace_id,
        "sourceType": req.source_type.value if hasattr(req.source_type, "value") else req.source_type,
        "sourceId": req.source_id,
        "status": req.status.value if hasattr(req.status, "value") else req.status,
        "requestedByUserId": req.requested_by_user_id,
        "decidedByUserId": req.decided_by_user_id,
    }