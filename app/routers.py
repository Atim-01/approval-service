from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth import Principal, get_principal, require
from app.database import get_db
from app.idempotency import get_cached_response, store_response
from app.models import ApprovalStatus
from app.schemas import (
    ApprovalRequestCreate,
    ApprovalRequestOut,
    ApprovalRequestList,
)
from app import services

router = APIRouter(prefix="/v1/approval-requests", tags=["approval-requests"])


@router.post("", response_model=ApprovalRequestOut, status_code=status.HTTP_201_CREATED)
def create_request(
    payload: ApprovalRequestCreate,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    require(principal, "approval:create")

    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header is required to create an approval request",
        )

    body_dict = payload.model_dump(mode="json")
    cached = get_cached_response(db, principal.workspace_id, "create_request", idempotency_key, body_dict)
    if cached is not None:
        code, cached_body = cached
        if code >= 400:
            raise HTTPException(status_code=code, detail=cached_body.get("detail", "cached error"))
        return cached_body

    req = services.create_approval_request(db, principal.workspace_id, principal.user_id, payload)
    out = ApprovalRequestOut.from_model(req)
    out_dict = out.model_dump(mode="json")

    store_response(
        db, principal.workspace_id, "create_request", idempotency_key, body_dict,
        status.HTTP_201_CREATED, out_dict,
    )
    db.commit()
    return out


@router.get("", response_model=ApprovalRequestList)
def list_requests(
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
    status_filter: Optional[ApprovalStatus] = Query(default=None, alias="status"),
    sourceType: Optional[str] = Query(default=None),
    sourceId: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    require(principal, "approval:read")
    items, total = services.list_approval_requests(
        db,
        principal.workspace_id,
        status_filter=status_filter,
        source_type=sourceType,
        source_id=sourceId,
        limit=limit,
        offset=offset,
    )
    return ApprovalRequestList(
        items=[ApprovalRequestOut.from_model(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{request_id}", response_model=ApprovalRequestOut)
def get_request(
    request_id: str,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    require(principal, "approval:read")
    req = services.get_approval_request(db, principal.workspace_id, request_id)
    return ApprovalRequestOut.from_model(req)