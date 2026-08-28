"""SQLAlchemy ORM models."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    JSON,
    Column,
    DateTime,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from .database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ServiceRequest(Base):
    __tablename__ = "service_requests"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_number = Column(String(64), unique=True, nullable=False, index=True)
    department = Column(String(128), nullable=False, index=True)
    status = Column(String(64), nullable=False, default="open", index=True)
    data = Column(JSON, nullable=True, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    __table_args__ = (
        Index("ix_sr_dept_status", "department", "status"),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    action = Column(String(32), nullable=False)
    request_id = Column(PG_UUID(as_uuid=True), nullable=False, index=True)
    old_data = Column(JSON, nullable=True)
    new_data = Column(JSON, nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

class UserSetting(Base):
    __tablename__ = "user_settings"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(254), unique=True, nullable=False, index=True)
    display_name = Column(String(128), nullable=False, default="")
    role = Column(String(32), nullable=False, default="user")
    theme = Column(String(32), nullable=False, default="light")
    density = Column(String(16), nullable=False, default="default")
    sidebar = Column(String(16), nullable=False, default="visible")
    notifications = Column(String(16), nullable=False, default="on")
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )


class ContractService(Base):
    """One editable service row from the workbook's XXX sheet."""

    __tablename__ = "contract_services"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contract_no = Column(String(128), nullable=False, index=True)
    # Keep this nullable so rows created before RBQ enforcement remain
    # representable.  All API-created rows populate it, and the unique index
    # below is the final guard against concurrent duplicate writes.
    rbq_no = Column(Text, nullable=True)
    fields = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    __table_args__ = (
        Index("ix_contract_services_contract_updated", "contract_no", "updated_at"),
        Index("uq_contract_services_rbq_no", "rbq_no", unique=True),
    )
