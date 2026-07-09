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

def create_approval_request(
    db: Session, workspace_id: str, actor_user_id: str, payload: ApprovalRequestCreate
) -> ApprovalRequest:
    req = ApprovalRequest(
        workspace_id=workspace_id,
        source_type=payload.sourceType,
        source_id=payload.sourceId,
        reviewer_user_ids=payload.reviewerUserIds,
        requested_by_user_id=actor_user_id,
        status=ApprovalStatus.pending,
        title=payload.title,
        description=payload.description,
        request_metadata=payload.metadata,
    )
    db.add(req)
    db.flush()  # populate req.id before we reference it below

    _write_audit(
        db,
        workspace_id=workspace_id,
        approval_request_id=req.id,
        actor_user_id=actor_user_id,
        action="created",
        from_status=None,
        to_status=ApprovalStatus.pending.value,
        details={"sourceType": payload.sourceType.value, "sourceId": payload.sourceId},
    )
    _write_outbox(
        db,
        workspace_id=workspace_id,
        approval_request_id=req.id,
        event_type="approval_request.created",
        payload=_event_payload(req),
    )
    return req

def get_approval_request(db: Session, workspace_id: str, request_id: str) -> ApprovalRequest:
    req = (
        db.query(ApprovalRequest)
        .filter(ApprovalRequest.id == request_id, ApprovalRequest.workspace_id == workspace_id)
        .first()
    )
    if req is None:
        # Same 404 whether the id doesn't exist at all or belongs to another
        # workspace - never reveal cross-workspace existence.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="approval request not found")
    return req


def list_approval_requests(
    db: Session,
    workspace_id: str,
    *,
    status_filter: Optional[ApprovalStatus] = None,
    source_type: Optional[str] = None,
    source_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[ApprovalRequest], int]:
    q = db.query(ApprovalRequest).filter(ApprovalRequest.workspace_id == workspace_id)
    if status_filter is not None:
        q = q.filter(ApprovalRequest.status == status_filter)
    if source_type is not None:
        q = q.filter(ApprovalRequest.source_type == source_type)
    if source_id is not None:
        q = q.filter(ApprovalRequest.source_id == source_id)

    total = q.count()
    items = (
        q.order_by(ApprovalRequest.created_at.desc()).offset(offset).limit(limit).all()
    )
    return items, total

def _ensure_transitionable(req: ApprovalRequest) -> None:
    if req.status in FINAL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"approval request is already in a final state: {req.status.value}",
        )


def decide(
    db: Session,
    *,
    workspace_id: str,
    request_id: str,
    actor_user_id: str,
    new_status: ApprovalStatus,
    reason: Optional[str],
) -> ApprovalRequest:
    req = get_approval_request(db, workspace_id, request_id)
    _ensure_transitionable(req)

    from_status = req.status.value
    req.status = new_status
    req.decision_reason = reason
    req.decided_by_user_id = actor_user_id
    req.decided_at = datetime.utcnow()

    action = {
        ApprovalStatus.approved: "approved",
        ApprovalStatus.rejected: "rejected",
        ApprovalStatus.cancelled: "cancelled",
    }[new_status]

    _write_audit(
        db,
        workspace_id=workspace_id,
        approval_request_id=req.id,
        actor_user_id=actor_user_id,
        action=action,
        from_status=from_status,
        to_status=new_status.value,
        details={"reason": reason} if reason else None,
    )
    _write_outbox(
        db,
        workspace_id=workspace_id,
        approval_request_id=req.id,
        event_type=f"approval_request.{action}",
        payload=_event_payload(req),
    )
    db.flush()
    return req