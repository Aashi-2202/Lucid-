"""Job draft database model."""

import re
from datetime import datetime

from sqlalchemy import String, Text, Integer, ForeignKey, DateTime, func, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Job(Base):
    """A job description draft linked to a recruiter."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    recruiter_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("recruiters.id"), index=True
    )
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    folder_link: Mapped[str] = mapped_column(String(1024))
    folder_id: Mapped[str] = mapped_column(String(255))
    folder_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    folder_pdf_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    additional_competencies: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]")
    status: Mapped[str] = mapped_column(
        String(20), default="draft", server_default="draft"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    recruiter: Mapped["Recruiter"] = relationship(back_populates="jobs")  # noqa: F821
    skills: Mapped[list["SkillRequirement"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


def extract_folder_id(folder_link: str) -> str | None:
    """
    Extract the Google Drive folder ID from various URL formats.

    Supported:
    - https://drive.google.com/drive/folders/FOLDER_ID
    - https://drive.google.com/drive/u/0/folders/FOLDER_ID
    - https://drive.google.com/drive/folders/FOLDER_ID?usp=sharing
    - Raw folder ID string
    """
    patterns = [
        r"folders/([a-zA-Z0-9_-]+)",  # Standard folder URL
        r"^([a-zA-Z0-9_-]{20,})$",     # Raw folder ID (20+ chars)
    ]
    for pattern in patterns:
        match = re.search(pattern, folder_link.strip())
        if match:
            return match.group(1)
    return None
