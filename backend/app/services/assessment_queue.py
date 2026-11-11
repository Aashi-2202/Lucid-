"""Durable leases and fenced commits; no database transaction held during IO."""

import asyncio
from dataclasses import dataclass
from datetime import timedelta
import logging
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import func, or_, select, update

from app.models.assessment import Assessment, AssessmentFile
from app.schemas.assessments import IntakeSnapshot, SourceFile, WorkerRequest, Discovered, Ready, Excluded, Failed
from app.services.intake_runner import run_isolated


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Claim:
    assessment_id: str
    token: str
    request: WorkerRequest
    file_id: int | None = None


async def database_time(db):
    # Database time avoids relying on clocks matching across worker hosts.
    return (await db.execute(select(func.current_timestamp()))).scalar_one()


async def claim_next(sessions) -> Claim | None:
    async with sessions.begin() as db:
        now = await database_time(db)
        # Timeout is frozen per run. Take a short lease first while constructing
        # the request, then extend it atomically within this transaction.
        token = str(uuid4())
        result = await db.execute(
            update(Assessment).where(
                Assessment.active_slot == 1,
                or_(Assessment.lease_token.is_(None), Assessment.lease_expires_at <= now),
            ).values(lease_token=token, lease_expires_at=now + timedelta(seconds=30), status="running")
            .returning(Assessment.id)
        )
        assessment_id = result.scalar_one_or_none()
        if assessment_id is None:
            return None
        run = await db.get(Assessment, assessment_id)
        try:
            snapshot = IntakeSnapshot.model_validate(run.snapshot)
        except ValidationError:
            _fail_run(run, now, Failed(code="unsupported_snapshot", message="The saved configuration is invalid or unsupported."))
            return None
        run.lease_expires_at = now + timedelta(seconds=snapshot.file_timeout_seconds + 30)
        if not run.discovered:
            return Claim(run.id, token, WorkerRequest(action="discover", snapshot=snapshot))
        file = (await db.execute(
            select(AssessmentFile).where(AssessmentFile.assessment_id == run.id, AssessmentFile.status == "pending")
            .order_by(AssessmentFile.position).limit(1)
        )).scalar_one_or_none()
        if file is None:
            _finish_run(run, now)
            return None
        run.current_file_name = file.name
        try:
            source = SourceFile.model_validate(file.source_metadata)
        except ValidationError:
            _fail_run(run, now, Failed(code="invalid_file_metadata", message="The saved file metadata is invalid."))
            return None
        return Claim(run.id, token, WorkerRequest(action="screen", snapshot=snapshot,
                     file=source), file.id)


def _release(run):
    run.lease_token = None
    run.lease_expires_at = None
    run.current_file_name = None


def _finish_run(run, now):
    _release(run)
    run.status = "screened"
    run.active_slot = None
    run.finished_at = now


def _fail_run(run, now, result):
    _release(run)
    run.status = "failed"
    run.active_slot = None
    run.finished_at = now
    run.error_code = result.code
    run.error_message = result.message


async def save_outcome(sessions, claim: Claim, outcome) -> bool:
    async with sessions.begin() as db:
        now = await database_time(db)
        # Claim the write itself before touching a file. A late worker cannot
        # save after expiry or after another worker replaced its token.
        fence = (await db.execute(
            update(Assessment).where(
                Assessment.id == claim.assessment_id, Assessment.active_slot == 1,
                Assessment.lease_token == claim.token, Assessment.lease_expires_at > now,
            ).values(lease_expires_at=now + timedelta(seconds=30)).returning(Assessment.id)
        )).scalar_one_or_none()
        if fence is None:
            return False
        run = await db.get(Assessment, claim.assessment_id)
        if claim.file_id is None:
            if not isinstance(outcome, Discovered):
                _fail_run(run, now, outcome if isinstance(outcome, Failed) else
                          Failed(code="worker_error", message="Folder discovery returned an invalid result."))
                return True
            if not outcome.files or len(outcome.files) > claim.request.snapshot.max_files or len({f.id for f in outcome.files}) != len(outcome.files):
                _fail_run(run, now, Failed(code="invalid_file_list", message="Folder discovery returned an invalid file list."))
                return True
            for position, file in enumerate(outcome.files):
                db.add(AssessmentFile(assessment_id=run.id, position=position, drive_file_id=file.id,
                                     name=file.name, version=file.version, source_metadata=file.model_dump()))
            run.discovered = True
            run.total_files = len(outcome.files)
            _release(run)
            return True
        file = await db.get(AssessmentFile, claim.file_id)
        if file is None or file.assessment_id != run.id or file.status != "pending":
            return False
        if isinstance(outcome, Ready):
            file.status = "ready_for_analysis"
            file.document = outcome.document.model_dump(mode="json")
        elif isinstance(outcome, Excluded):
            file.status = "excluded"
            file.missing_skills = outcome.missing_skills
        else:
            failure = outcome if isinstance(outcome, Failed) else Failed(code="worker_error", message="The worker returned an invalid file result.")
            file.status = "failed"
            file.error_code, file.error_message = failure.code, failure.message
        file.finished_at = now
        await db.flush()
        pending = (await db.execute(select(func.count()).select_from(AssessmentFile).where(
            AssessmentFile.assessment_id == run.id, AssessmentFile.status == "pending",
        ))).scalar_one()
        if not pending:
            _finish_run(run, now)
        else:
            _release(run)
        return True


async def release_claim(sessions, claim: Claim):
    async with sessions.begin() as db:
        await db.execute(update(Assessment).where(
            Assessment.id == claim.assessment_id, Assessment.lease_token == claim.token,
        ).values(lease_token=None, lease_expires_at=None, current_file_name=None))


async def process_one(sessions, runner=run_isolated) -> bool:
    claim = await claim_next(sessions)
    if claim is None:
        return False
    try:
        outcome = await runner(claim.request)
        return await save_outcome(sessions, claim, outcome)
    finally:
        # A crash leaves the DB lease to expire. Normal cancellation can release
        # it immediately after run_isolated has killed its child.
        await release_claim(sessions, claim)


async def worker_loop(sessions, poll_seconds: float):
    while True:
        try:
            if await process_one(sessions):
                continue
        except asyncio.CancelledError:
            raise
        except Exception:
            # Do not log exceptions containing SQL parameters or candidate data.
            logger.error("Assessment queue operation failed; retrying after the poll interval.")
        await asyncio.sleep(poll_seconds)
