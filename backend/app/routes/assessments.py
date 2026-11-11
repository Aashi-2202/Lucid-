"""Authenticated assessment initiation, immutable inputs, and intake progress."""

from uuid import UUID, uuid4
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_recruiter
from app.models.assessment import Assessment, AssessmentFile
from app.models.job import Job
from app.models.recruiter import Recruiter
from app.schemas.assessments import AssessmentProgress, IntakeSnapshot, ResumeDocument, SkillSnapshot, StartAssessmentRequest
from app.services.mandatory_gate import GateRequirement


router = APIRouter(tags=["assessments"])


async def owned_run(assessment_id, recruiter_id, db):
    run = (await db.execute(select(Assessment).where(
        Assessment.id == str(assessment_id), Assessment.recruiter_id == recruiter_id,
    ))).scalar_one_or_none()
    if run is None:
        raise HTTPException(404, "Assessment not found")
    return run


async def progress(run, db) -> AssessmentProgress:
    rows = (await db.execute(select(AssessmentFile.status, func.count()).where(
        AssessmentFile.assessment_id == run.id,
    ).group_by(AssessmentFile.status))).all()
    counts = dict(rows)
    terminal = ("ready_for_analysis", "excluded", "failed")
    phase = run.status if run.status in ("screened", "failed") else "screening" if run.discovered else "discovery"
    return AssessmentProgress(
        id=run.id, job_id=run.job_id, status=run.status, phase=phase,
        total_files=run.total_files, processed_files=sum(counts.get(k, 0) for k in terminal),
        ready_for_analysis=counts.get("ready_for_analysis", 0), excluded=counts.get("excluded", 0),
        failed=counts.get("failed", 0), current_file_name=run.current_file_name,
        error_code=run.error_code, error_message=run.error_message,
        created_at=run.created_at, finished_at=run.finished_at,
    )


@router.post("/jobs/{job_id}/assessments", response_model=AssessmentProgress, status_code=202)
async def start_assessment(
    job_id: int, body: StartAssessmentRequest, response: Response,
    recruiter: Recruiter = Depends(get_current_recruiter), db: AsyncSession = Depends(get_db),
):
    key = str(body.idempotency_key)
    recruiter_id = recruiter.id
    existing = (await db.execute(select(Assessment).where(
        Assessment.recruiter_id == recruiter_id, Assessment.idempotency_key == key,
    ))).scalar_one_or_none()
    if existing is not None:
        if existing.job_id != job_id:
            raise HTTPException(409, "This request key was already used for another job")
        response.headers["Location"] = f"/assessments/{existing.id}"
        return await progress(existing, db)

    # A single joined query gives a consistent job/requirements snapshot.
    job = (await db.execute(select(Job).options(joinedload(Job.skills)).where(
        Job.id == job_id, Job.recruiter_id == recruiter_id,
    ))).unique().scalar_one_or_none()
    if job is None:
        raise HTTPException(404, "Job not found")
    if job.status != "draft" or not job.title.strip() or not job.description.strip() or not job.skills:
        raise HTTPException(422, "Save a draft with job details and at least one skill before starting")
    try:
        skills = []
        for skill in sorted(job.skills, key=lambda s: s.id):
            GateRequirement(skill.skill, skill.mandatory, tuple(skill.aliases or ()))
            skills.append(SkillSnapshot(
                skill=skill.skill, description=skill.description, mandatory=skill.mandatory,
                importance=skill.importance, required_evidence_level=skill.required_evidence_level,
                assessment_method=skill.assessment_method, aliases=skill.aliases or [],
            ))
        snapshot = IntakeSnapshot(
            title=job.title, description=job.description, company=job.company,
            folder_id=job.folder_id, folder_link=job.folder_link, skills=skills,
            max_files=settings.assessment_max_files, file_timeout_seconds=settings.assessment_file_timeout_seconds,
            embedding_model=settings.embedding_model,
            relevance_thresholds=[settings.relevance_bucket_none, settings.relevance_bucket_weak,
                                  settings.relevance_bucket_moderate, settings.relevance_bucket_strong],
        )
    except (ValidationError, ValueError):
        raise HTTPException(422, "The saved skill or folder configuration is invalid")
    run = Assessment(id=str(uuid4()), job_id=job.id, recruiter_id=recruiter_id,
                     idempotency_key=key, snapshot=snapshot.model_dump(mode="json"))
    db.add(run)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        # Concurrent retries of the same request return the original run.
        existing = (await db.execute(select(Assessment).where(
            Assessment.recruiter_id == recruiter_id, Assessment.idempotency_key == key,
        ))).scalar_one_or_none()
        if existing is not None and existing.job_id == job_id:
            response.headers["Location"] = f"/assessments/{existing.id}"
            return await progress(existing, db)
        raise HTTPException(409, "An assessment is already active or the job changed. Retry after it finishes.")
    await db.refresh(run)
    response.headers["Location"] = f"/assessments/{run.id}"
    return await progress(run, db)


@router.get("/jobs/{job_id}/assessments", response_model=list[AssessmentProgress])
async def list_assessments(
    job_id: int, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
    recruiter: Recruiter = Depends(get_current_recruiter), db: AsyncSession = Depends(get_db),
):
    job = (await db.execute(select(Job.id).where(Job.id == job_id, Job.recruiter_id == recruiter.id))).scalar_one_or_none()
    if job is None:
        raise HTTPException(404, "Job not found")
    runs = (await db.execute(select(Assessment).where(
        Assessment.job_id == job_id, Assessment.recruiter_id == recruiter.id,
    ).order_by(Assessment.created_at.desc(), Assessment.id).offset(offset).limit(limit))).scalars().all()
    return [await progress(run, db) for run in runs]


@router.get("/assessments/{assessment_id}", response_model=AssessmentProgress)
async def get_assessment(
    assessment_id: UUID, recruiter: Recruiter = Depends(get_current_recruiter), db: AsyncSession = Depends(get_db),
):
    return await progress(await owned_run(assessment_id, recruiter.id, db), db)


@router.get("/assessments/{assessment_id}/snapshot")
async def get_snapshot(
    assessment_id: UUID, recruiter: Recruiter = Depends(get_current_recruiter), db: AsyncSession = Depends(get_db),
):
    return (await owned_run(assessment_id, recruiter.id, db)).snapshot


class FileProgress(BaseModel):
    id: int
    name: str
    status: Literal["pending", "ready_for_analysis", "excluded", "failed"]
    missing_skills: list[str]
    error_code: str | None
    error_message: str | None

    model_config = {"from_attributes": True}


@router.get("/assessments/{assessment_id}/files", response_model=list[FileProgress])
async def list_files(
    assessment_id: UUID, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
    status: Literal["pending", "ready_for_analysis", "excluded", "failed"] | None = None,
    recruiter: Recruiter = Depends(get_current_recruiter), db: AsyncSession = Depends(get_db),
):
    run = await owned_run(assessment_id, recruiter.id, db)
    query = select(AssessmentFile).where(AssessmentFile.assessment_id == run.id)
    if status is not None:
        query = query.where(AssessmentFile.status == status)
    files = (await db.execute(query.order_by(AssessmentFile.position).offset(offset).limit(limit))).scalars().all()
    return files


class FileDetail(FileProgress):
    drive_file_id: str
    version: str
    document: ResumeDocument | None


@router.get("/assessments/{assessment_id}/files/{file_id}", response_model=FileDetail)
async def get_file(
    assessment_id: UUID, file_id: int,
    recruiter: Recruiter = Depends(get_current_recruiter), db: AsyncSession = Depends(get_db),
):
    run = await owned_run(assessment_id, recruiter.id, db)
    file = (await db.execute(select(AssessmentFile).where(
        AssessmentFile.id == file_id, AssessmentFile.assessment_id == run.id,
    ))).scalar_one_or_none()
    if file is None:
        raise HTTPException(404, "File not found")
    return file
