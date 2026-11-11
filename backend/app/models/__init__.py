"""Register all models so SQLAlchemy metadata picks them up."""

from app.models.recruiter import Recruiter
from app.models.job import Job
from app.models.skill import SkillRequirement

__all__ = ["Recruiter", "Job", "SkillRequirement"]
