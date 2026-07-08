import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    DateTime,
    JSON,
    Enum as SAEnum,
    Index,
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