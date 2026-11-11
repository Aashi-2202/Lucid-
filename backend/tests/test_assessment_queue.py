import asyncio
from datetime import timedelta
from dataclasses import asdict

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.models import Assessment, AssessmentFile, Job
from app.schemas.assessments import Failed, Ready, Excluded
from app.services.assessment_queue import claim_next, save_outcome, process_one, database_time, release_claim
from app.services.pdf import extract_pdf
from queue_helpers import QueueTestCase, discovery
from test_pdf import make_pdf, RESUME_TEXT


class AssessmentQueueTests(QueueTestCase):
    async def test_database_enforces_one_active_assessment(self):
        await self.enqueue()
        with self.assertRaises(IntegrityError):
            await self.enqueue()

    async def test_discovery_is_frozen_once_and_files_process_in_order(self):
        run_id = await self.enqueue()
        calls = []

        async def runner(request):
            calls.append(request.action if request.file is None else request.file.id)
            if request.action == "discover":
                return discovery("a", "b", "c")
            if request.file.id == "a":
                return Ready(document=asdict(extract_pdf(make_pdf(RESUME_TEXT))))
            if request.file.id == "b":
                return Excluded(missing_skills=["Python"])
            return Failed(code="encrypted_pdf", message="Password protected.")

        for _ in range(4):
            self.assertTrue(await process_one(self.sessions, runner))
        self.assertFalse(await process_one(self.sessions, runner))
        self.assertEqual(calls, ["discover", "a", "b", "c"])
        async with self.sessions() as db:
            run = await db.get(Assessment, run_id)
            self.assertEqual(run.status, "screened")
            self.assertIsNone(run.active_slot)
            files = (await db.execute(select(AssessmentFile).order_by(AssessmentFile.position))).scalars().all()
            self.assertEqual([f.status for f in files], ["ready_for_analysis", "excluded", "failed"])
            self.assertIsNotNone(files[0].document)
            self.assertIsNone(files[1].document)
            self.assertIsNone(files[2].document)
        # Finishing this run releases the deployment-wide slot.
        await self.enqueue()

    async def test_competing_workers_cannot_claim_the_same_operation(self):
        await self.enqueue()
        claims = await asyncio.gather(claim_next(self.sessions), claim_next(self.sessions))
        self.assertEqual(sum(claim is not None for claim in claims), 1)

    async def test_expired_lease_recovers_and_old_worker_cannot_write(self):
        run_id = await self.enqueue()
        old_claim = await claim_next(self.sessions)
        async with self.sessions.begin() as db:
            now = await database_time(db)
            await db.execute(update(Assessment).where(Assessment.id == run_id)
                             .values(lease_expires_at=now - timedelta(seconds=1)))
        new_claim = await claim_next(self.sessions)
        self.assertIsNotNone(new_claim)
        self.assertNotEqual(old_claim.token, new_claim.token)
        self.assertFalse(await save_outcome(self.sessions, old_claim, discovery("old")))
        await release_claim(self.sessions, old_claim)
        self.assertTrue(await save_outcome(self.sessions, new_claim, discovery("new")))
        async with self.sessions() as db:
            files = (await db.execute(select(AssessmentFile))).scalars().all()
            self.assertEqual([f.drive_file_id for f in files], ["new"])

    async def test_expired_worker_cannot_save_even_without_replacement(self):
        run_id = await self.enqueue()
        claim = await claim_next(self.sessions)
        async with self.sessions.begin() as db:
            now = await database_time(db)
            await db.execute(update(Assessment).where(Assessment.id == run_id)
                             .values(lease_expires_at=now - timedelta(seconds=1)))
        self.assertFalse(await save_outcome(self.sessions, claim, discovery("a")))

    async def test_completed_file_checkpoint_survives_database_reopen(self):
        run_id = await self.enqueue()
        claim = await claim_next(self.sessions)
        await save_outcome(self.sessions, claim, discovery("a", "b"))
        claim = await claim_next(self.sessions)
        await save_outcome(self.sessions, claim, Excluded(missing_skills=["Python"]))
        await self.engine.dispose()
        self.open_engine()
        next_claim = await claim_next(self.sessions)
        self.assertEqual(next_claim.request.file.id, "b")
        async with self.sessions() as db:
            run = await db.get(Assessment, run_id)
            self.assertEqual(run.total_files, 2)

    async def test_worker_uses_snapshot_after_draft_is_edited(self):
        await self.enqueue()
        async with self.sessions.begin() as db:
            job = await db.get(Job, 1)
            job.title, job.folder_id = "Changed", "changed_folder"
        claim = await claim_next(self.sessions)
        self.assertEqual(claim.request.snapshot.title, "Backend developer")
        self.assertEqual(claim.request.snapshot.folder_id, "job_folder")

    async def test_cancelled_worker_releases_lease_without_completing_file(self):
        run_id = await self.enqueue()
        started = asyncio.Event()

        async def runner(_):
            started.set()
            await asyncio.Event().wait()

        task = asyncio.create_task(process_one(self.sessions, runner))
        await started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        async with self.sessions() as db:
            run = await db.get(Assessment, run_id)
            self.assertIsNone(run.lease_token)
            self.assertFalse(run.discovered)
        self.assertIsNotNone(await claim_next(self.sessions))

    async def test_discovery_failure_releases_slot_and_records_safe_reason(self):
        run_id = await self.enqueue()
        claim = await claim_next(self.sessions)
        await save_outcome(self.sessions, claim, Failed(code="no_pdfs", message="No PDFs found."))
        async with self.sessions() as db:
            run = await db.get(Assessment, run_id)
            self.assertEqual(run.status, "failed")
            self.assertEqual(run.error_code, "no_pdfs")
            self.assertIsNone(run.active_slot)
        await self.enqueue()

    async def test_unsupported_snapshot_fails_without_loading_live_job(self):
        run_id = await self.enqueue()
        async with self.sessions.begin() as db:
            run = await db.get(Assessment, run_id)
            run.snapshot = {**run.snapshot, "gate_version": "unknown-v2"}
        self.assertIsNone(await claim_next(self.sessions))
        async with self.sessions() as db:
            run = await db.get(Assessment, run_id)
            self.assertEqual(run.status, "failed")
            self.assertEqual(run.error_code, "unsupported_snapshot")

    async def test_duplicate_discovery_list_fails_atomically(self):
        run_id = await self.enqueue()
        claim = await claim_next(self.sessions)
        await save_outcome(self.sessions, claim, discovery("a", "a"))
        async with self.sessions() as db:
            run = await db.get(Assessment, run_id)
            self.assertEqual(run.status, "failed")
            self.assertEqual((await db.execute(select(AssessmentFile))).scalars().all(), [])

    async def test_oversize_discovery_list_fails_before_any_files_are_saved(self):
        run_id = await self.enqueue()
        claim = await claim_next(self.sessions)
        await save_outcome(self.sessions, claim, discovery(*(f"file_{i}" for i in range(101))))
        async with self.sessions() as db:
            run = await db.get(Assessment, run_id)
            self.assertEqual(run.status, "failed")
            self.assertEqual((await db.execute(select(AssessmentFile))).scalars().all(), [])

    async def test_same_claim_cannot_save_twice(self):
        await self.enqueue()
        claim = await claim_next(self.sessions)
        self.assertTrue(await save_outcome(self.sessions, claim, discovery("a")))
        self.assertFalse(await save_outcome(self.sessions, claim, discovery("a")))
