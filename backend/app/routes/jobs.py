"""Job routes — create, list, update, and folder access check."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.dependencies import get_current_recruiter
from app.models.job import Job, extract_folder_id
from app.models.recruiter import Recruiter
from app.models.skill import SkillRequirement
from app.services.drive import (
    FolderError,
    FolderInfo,
    check_folder_access,
    get_service_account_email,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])


# ── Schemas ──────────────────────────────────────────────────────────


class CreateJobRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    folder_link: str = Field(min_length=1)
    company: str | None = None


class UpdateJobRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    folder_link: str | None = None
    company: str | None = None


class SkillInput(BaseModel):
    skill: str = Field(min_length=1, max_length=255)
    description: str | None = None
    mandatory: bool = False
    importance: int = Field(default=3, ge=1, le=5)
    required_evidence_level: int = Field(default=1, ge=1, le=5)
    assessment_method: str = Field(default="resume", pattern="^(resume|interview)$")
    aliases: list[str] | None = None


class SkillResponse(BaseModel):
    id: int
    skill: str
    description: str | None
    mandatory: bool
    importance: int
    required_evidence_level: int
    assessment_method: str
    aliases: list[str] | None

    model_config = {"from_attributes": True}


class JobResponse(BaseModel):
    id: int
    title: str
    description: str
    folder_link: str
    folder_id: str
    folder_name: str | None
    folder_pdf_count: int | None
    company: str | None
    recruiter_email: str
    status: str
    skills: list[SkillResponse] = []

    model_config = {"from_attributes": True}


class JobSummary(BaseModel):
    id: int
    title: str
    company: str | None
    status: str
    folder_pdf_count: int | None

    model_config = {"from_attributes": True}


class FolderCheckResponse(BaseModel):
    success: bool
    folder_name: str | None = None
    pdf_count: int | None = None
    error: str | None = None


class ServiceAccountResponse(BaseModel):
    email: str


# ── Routes ───────────────────────────────────────────────────────────


@router.get("/service-account", response_model=ServiceAccountResponse)
async def get_service_account(
    recruiter: Recruiter = Depends(get_current_recruiter),
):
    """Return the service account email so recruiters can share folders with it."""
    try:
        email = get_service_account_email()
        return ServiceAccountResponse(email=email)
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Service account not configured — contact the administrator",
        )


@router.post("", response_model=JobResponse, status_code=201)
async def create_job(
    body: CreateJobRequest,
    recruiter: Recruiter = Depends(get_current_recruiter),
    db: AsyncSession = Depends(get_db),
):
    """Create a new job draft linked to the recruiter."""
    folder_id = extract_folder_id(body.folder_link)
    if not folder_id:
        raise HTTPException(
            status_code=400,
            detail="Could not extract a folder ID from the provided link. "
                   "Use a Google Drive folder URL or paste the folder ID directly.",
        )

    job = Job(
        recruiter_id=recruiter.id,
        title=body.title,
        description=body.description,
        folder_link=body.folder_link,
        folder_id=folder_id,
        company=body.company,
        status="draft",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job, attribute_names=["skills"])

    return _job_to_response(job, recruiter.email)


@router.get("", response_model=list[JobSummary])
async def list_jobs(
    recruiter: Recruiter = Depends(get_current_recruiter),
    db: AsyncSession = Depends(get_db),
):
    """List all jobs for the authenticated recruiter."""
    result = await db.execute(
        select(Job)
        .where(Job.recruiter_id == recruiter.id)
        .order_by(Job.updated_at.desc())
    )
    jobs = result.scalars().all()
    return [JobSummary.model_validate(j) for j in jobs]


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: int,
    recruiter: Recruiter = Depends(get_current_recruiter),
    db: AsyncSession = Depends(get_db),
):
    """Get a job by ID. Only the owning recruiter can access it."""
    job = await _get_job_for_recruiter(job_id, recruiter.id, db)
    return _job_to_response(job, recruiter.email)


@router.patch("/{job_id}", response_model=JobResponse)
async def update_job(
    job_id: int,
    body: UpdateJobRequest,
    recruiter: Recruiter = Depends(get_current_recruiter),
    db: AsyncSession = Depends(get_db),
):
    """Update a draft job. Only draft jobs can be edited."""
    job = await _get_job_for_recruiter(job_id, recruiter.id, db)

    if job.status != "draft":
        raise HTTPException(
            status_code=400,
            detail="Only draft jobs can be edited",
        )

    if body.title is not None:
        job.title = body.title
    if body.description is not None:
        job.description = body.description
    if body.company is not None:
        job.company = body.company
    if body.folder_link is not None:
        folder_id = extract_folder_id(body.folder_link)
        if not folder_id:
            raise HTTPException(status_code=400, detail="Invalid folder link")
        job.folder_link = body.folder_link
        job.folder_id = folder_id
        job.folder_name = None
        job.folder_pdf_count = None

    await db.commit()
    await db.refresh(job, attribute_names=["skills"])
    return _job_to_response(job, recruiter.email)


@router.post("/{job_id}/check-folder", response_model=FolderCheckResponse)
async def check_job_folder(
    job_id: int,
    recruiter: Recruiter = Depends(get_current_recruiter),
    db: AsyncSession = Depends(get_db),
):
    """Check that the service account can access the job's folder."""
    job = await _get_job_for_recruiter(job_id, recruiter.id, db)

    result = check_folder_access(job.folder_id)

    if isinstance(result, FolderError):
        return FolderCheckResponse(
            success=False,
            error=result.message,
        )

    # Update job with folder metadata
    job.folder_name = result.name
    job.folder_pdf_count = result.pdf_count
    await db.commit()

    return FolderCheckResponse(
        success=True,
        folder_name=result.name,
        pdf_count=result.pdf_count,
    )


# ── Skills sub-routes ────────────────────────────────────────────────


@router.put("/{job_id}/skills", response_model=list[SkillResponse])
async def set_skills(
    job_id: int,
    skills: list[SkillInput],
    recruiter: Recruiter = Depends(get_current_recruiter),
    db: AsyncSession = Depends(get_db),
):
    """
    Replace all skills for a job.
    Accepts the full list — removes old ones and inserts new ones.
    Only draft jobs can be edited.
    """
    job = await _get_job_for_recruiter(job_id, recruiter.id, db)

    if job.status != "draft":
        raise HTTPException(
            status_code=400, detail="Only draft jobs can be edited"
        )

    # Remove existing skills
    for existing in list(job.skills):
        await db.delete(existing)

    # Add new skills
    new_skills = []
    for s in skills:
        skill = SkillRequirement(
            job_id=job.id,
            skill=s.skill,
            description=s.description,
            mandatory=s.mandatory,
            importance=s.importance,
            required_evidence_level=s.required_evidence_level,
            assessment_method=s.assessment_method,
            aliases=s.aliases,
        )
        db.add(skill)
        new_skills.append(skill)

    await db.commit()
    for skill in new_skills:
        await db.refresh(skill)

    return [SkillResponse.model_validate(s) for s in new_skills]


@router.get("/{job_id}/skills", response_model=list[SkillResponse])
async def get_skills(
    job_id: int,
    recruiter: Recruiter = Depends(get_current_recruiter),
    db: AsyncSession = Depends(get_db),
):
    """Get all skill requirements for a job."""
    job = await _get_job_for_recruiter(job_id, recruiter.id, db)
    return [SkillResponse.model_validate(s) for s in job.skills]


# ── Helpers ──────────────────────────────────────────────────────────


async def _get_job_for_recruiter(
    job_id: int, recruiter_id: int, db: AsyncSession
) -> Job:
    """Load a job with skills, verifying ownership."""
    result = await db.execute(
        select(Job)
        .options(selectinload(Job.skills))
        .where(Job.id == job_id)
    )
    job = result.scalar_one_or_none()

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.recruiter_id != recruiter_id:
        raise HTTPException(status_code=403, detail="Access denied")

    return job


def _job_to_response(job: Job, recruiter_email: str) -> JobResponse:
    """Convert a Job ORM instance to an API response."""
    return JobResponse(
        id=job.id,
        title=job.title,
        description=job.description,
        folder_link=job.folder_link,
        folder_id=job.folder_id,
        folder_name=job.folder_name,
        folder_pdf_count=job.folder_pdf_count,
        company=job.company,
        recruiter_email=recruiter_email,
        status=job.status,
        skills=[SkillResponse.model_validate(s) for s in job.skills],
    )
