"""Skill requirement database model."""

from sqlalchemy import String, Text, Integer, Boolean, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import ARRAY

from app.core.database import Base


class SkillRequirement(Base):
    """A skill requirement configured for a job."""

    __tablename__ = "skill_requirements"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    skill: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    mandatory: Mapped[bool] = mapped_column(Boolean, default=False)
    importance: Mapped[int] = mapped_column(Integer, default=3)  # 1-5
    required_evidence_level: Mapped[int] = mapped_column(Integer, default=1)  # 1-5
    assessment_method: Mapped[str] = mapped_column(
        String(20), default="resume"  # "resume" or "interview"
    )
    aliases: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)

    # Relationship
    job: Mapped["Job"] = relationship(back_populates="skills")  # noqa: F821
