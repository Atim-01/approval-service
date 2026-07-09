from datetime import datetime
from typing import Optional, List, Any, Dict

from pydantic import BaseModel, Field, field_validator

from app.models import SourceType, ApprovalStatus

FORBIDDEN_METADATA_KEYS = {
    "token",
    "secret",
    "password",
    "api_key",
    "apikey",
    "email",
    "signed_url",
    "signedurl",
    "storage_key",
    "storagekey",
    "provider_url",
    "providerurl",
}


def _reject_sensitive_keys(metadata: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not metadata:
        return metadata
    lowered = {k.lower().replace("-", "_") for k in metadata.keys()}
    hit = lowered & FORBIDDEN_METADATA_KEYS
    if hit:
        raise ValueError(f"metadata must not contain sensitive keys: {sorted(hit)}")
    return metadata


class ApprovalRequestCreate(BaseModel):
    sourceType: SourceType
    sourceId: str = Field(..., min_length=1, max_length=256)
    reviewerUserIds: List[str] = Field(default_factory=list)
    title: Optional[str] = Field(default=None, max_length=512)
    description: Optional[str] = Field(default=None, max_length=4000)
    metadata: Optional[Dict[str, Any]] = None

    @field_validator("metadata")
    @classmethod
    def no_sensitive_metadata(cls, v):
        return _reject_sensitive_keys(v)


class DecisionReject(BaseModel):
    reason: str = Field(..., min_length=1, max_length=2000)


class DecisionApprove(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=2000)


class DecisionCancel(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=2000)


class ApprovalRequestOut(BaseModel):
    id: str
    workspaceId: str
    sourceType: SourceType
    sourceId: str
    reviewerUserIds: List[str]
    requestedByUserId: str
    status: ApprovalStatus
    title: Optional[str]
    description: Optional[str]
    metadata: Optional[Dict[str, Any]]
    decisionReason: Optional[str]
    decidedByUserId: Optional[str]
    decidedAt: Optional[datetime]
    createdAt: datetime
    updatedAt: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, m):
        return cls(
            id=m.id,
            workspaceId=m.workspace_id,
            sourceType=m.source_type,
            sourceId=m.source_id,
            reviewerUserIds=m.reviewer_user_ids or [],
            requestedByUserId=m.requested_by_user_id,
            status=m.status,
            title=m.title,
            description=m.description,
            metadata=m.request_metadata,
            decisionReason=m.decision_reason,
            decidedByUserId=m.decided_by_user_id,
            decidedAt=m.decided_at,
            createdAt=m.created_at,
            updatedAt=m.updated_at,
        )


class ApprovalRequestList(BaseModel):
    items: List[ApprovalRequestOut]
    total: int
    limit: int
    offset: int


class ErrorResponse(BaseModel):
    error: str
    detail: str