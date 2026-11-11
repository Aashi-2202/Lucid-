"""Persistent, restartable intake queue. One active run across the deployment."""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Assessment(Base):
    __tablename__ = "assessments"
    __table_args__ = (
        UniqueConstraint("recruiter_id", "idempotency_key", name="uq_assessment_request"),
        UniqueConstraint("active_slot", name="uq_assessment_active_slot"),
        CheckConstraint(
            "(status IN ('queued', 'running') AND active_slot = 1 AND active_slot IS NOT NULL) OR "
            "(status IN ('screened', 'failed') AND active_slot IS NULL)", name="ck_assessment_active",
        ),
        CheckConstraint(
            "(lease_token IS NULL AND lease_expires_at IS NULL) OR "
            "(lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)", name="ck_assessment_lease",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    recruiter_id: Mapped[int] = mapped_column(ForeignKey("recruiters.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    active_slot: Mapped[int | None] = mapped_column(Integer, default=1, nullable=True)
    snapshot: Mapped[dict] = mapped_column(JSON)
    discovered: Mapped[bool] = mapped_column(Boolean, default=False)
    total_files: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lease_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_file_name: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AssessmentFile(Base):
    __tablename__ = "assessment_files"
    __table_args__ = (
        UniqueConstraint("assessment_id", "drive_file_id", name="uq_assessment_file"),
        UniqueConstraint("assessment_id", "position", name="uq_assessment_position"),
        CheckConstraint("status IN ('pending', 'ready_for_analysis', 'excluded', 'failed')", name="ck_file_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    drive_file_id: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(1024))
    version: Mapped[str] = mapped_column(String(255))
    source_metadata: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    missing_skills: Mapped[list] = mapped_column(JSON, default=list)
    document: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(512), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
