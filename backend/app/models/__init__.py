"""Register all models so SQLAlchemy metadata picks them up."""

from app.models.recruiter import Recruiter
from app.models.job import Job
from app.models.skill import SkillRequirement
from app.models.assessment import Assessment, AssessmentFile

__all__ = ["Recruiter", "Job", "SkillRequirement", "Assessment", "AssessmentFile"]
