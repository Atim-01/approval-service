import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    DateTime,
    JSON,
    Enum as SAEnum,
    Index,
    ForeignKey,
    Integer,
    UniqueConstraint,
)
from app.database import Base

import enum


def gen_uuid() -> str:
    return str(uuid.uuid4())


class SourceType(str, enum.Enum):
    publication = "publication"
    scenario = "scenario"
    edit = "edit"
    external = "external"


class ApprovalStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"


FINAL_STATUSES = {
    ApprovalStatus.approved,
    ApprovalStatus.rejected,
    ApprovalStatus.cancelled,
}


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    workspace_id = Column(String(128), nullable=False, index=True)

    source_type = Column(SAEnum(SourceType, native_enum=False, length=32), nullable=False)
    source_id = Column(String(256), nullable=False)

    reviewer_user_ids = Column(JSON, nullable=False, default=list)
    requested_by_user_id = Column(String(128), nullable=False)

    status = Column(
        SAEnum(ApprovalStatus, native_enum=False, length=32),
        nullable=False,
        default=ApprovalStatus.pending,
        index=True,
    )

    title = Column(String(512), nullable=True)
    description = Column(String(4000), nullable=True)
    request_metadata = Column(JSON, nullable=True)

    decision_reason = Column(String(2000), nullable=True)
    decided_by_user_id = Column(String(128), nullable=True)
    decided_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        Index(
            "ix_approval_requests_workspace_source",
            "workspace_id", "source_type", "source_id",
        ),
    )


class AuditLog(Base):
    """Immutable record of who changed what and when. Append-only."""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(String(128), nullable=False, index=True)
    approval_request_id = Column(
        String(36), ForeignKey("approval_requests.id"), nullable=False, index=True
    )
    actor_user_id = Column(String(128), nullable=False)
    action = Column(String(64), nullable=False)  # "created", "approved", "rejected", "cancelled"
    from_status = Column(String(32), nullable=True)
    to_status = Column(String(32), nullable=True)
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class OutboxEvent(Base):
    """Transactional outbox for future event-based integrations.

    Rows are written in the same DB transaction as the state change that
    produced them. A separate publisher process (not part of this
    assignment) would poll `published_at IS NULL`, publish to a broker,
    and mark the row published.
    """

    __tablename__ = "outbox_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(String(128), nullable=False, index=True)
    aggregate_type = Column(String(64), nullable=False, default="approval_request")
    aggregate_id = Column(String(36), nullable=False, index=True)
    event_type = Column(String(128), nullable=False)
    payload = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    published_at = Column(DateTime, nullable=True, index=True)

class IdempotencyRecord(Base):
    """Stores the outcome of a previously-processed idempotent request.

    Keyed on (workspace_id, endpoint, idempotency_key). A replayed request
    with the same key and same body hash gets the original response back
    instead of re-executing the side effect. A replayed key with a
    different body is rejected as a client error.
    """

    __tablename__ = "idempotency_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(String(128), nullable=False)
    endpoint = Column(String(128), nullable=False)
    idempotency_key = Column(String(256), nullable=False)
    request_hash = Column(String(64), nullable=False)
    response_status_code = Column(Integer, nullable=False)
    response_body = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "endpoint", "idempotency_key", name="uq_idempotency_scope"
        ),
    )