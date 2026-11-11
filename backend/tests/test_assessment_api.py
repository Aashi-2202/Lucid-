import asyncio
from unittest.mock import patch
from uuid import uuid4

import httpx
from sqlalchemy import select, delete

from app.core.auth import create_session_token
from app.core.database import get_db
from app.main import app
from app.models import Job, SkillRequirement
from app.schemas.assessments import Excluded, Failed
from app.services.assessment_queue import claim_next, save_outcome
from queue_helpers import QueueTestCase, discovery


class AssessmentApiTests(QueueTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()

        async def test_db():
            async with self.sessions() as db:
                yield db

        app.dependency_overrides[get_db] = test_db
        self.secret = patch("app.core.config.settings.jwt_secret", "testing-secret-" * 5)
        self.secret.start()
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
        self.headers = self.auth(1)

    def auth(self, recruiter):
        return {"Authorization": "Bearer " + create_session_token(recruiter, "test@example.test")}

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.clear()
        self.secret.stop()
        await super().asyncTearDown()

    async def start(self, key=None):
        return await self.client.post("/jobs/1/assessments", headers=self.headers,
                                      json={"idempotency_key": key or str(uuid4())})

    async def test_start_returns_202_and_repeat_key_returns_same_id(self):
        key = str(uuid4())
        first, second = await self.start(key), await self.start(key)
        self.assertEqual(first.status_code, 202, first.text)
        self.assertEqual(second.json()["id"], first.json()["id"])
        self.assertEqual(first.headers["Location"], "/assessments/" + first.json()["id"])
        self.assertEqual(first.json()["phase"], "discovery")
        self.assertIsNone(first.json()["total_files"])

    async def test_distinct_keys_cannot_start_two_active_runs(self):
        self.assertEqual((await self.start()).status_code, 202)
        self.assertEqual((await self.start()).status_code, 409)

    async def test_concurrent_duplicate_start_is_idempotent(self):
        key = str(uuid4())
        responses = await asyncio.gather(self.start(key), self.start(key))
        self.assertEqual([r.status_code for r in responses], [202, 202], [r.text for r in responses])
        self.assertEqual(responses[0].json()["id"], responses[1].json()["id"])

    async def test_requires_authentication_and_approved_account(self):
        response = await self.client.post("/jobs/1/assessments", json={"idempotency_key": str(uuid4())})
        self.assertIn(response.status_code, (401, 403))
        response = await self.client.post("/jobs/1/assessments", headers=self.auth(3), json={"idempotency_key": str(uuid4())})
        self.assertEqual(response.status_code, 403)

    async def test_other_recruiter_cannot_start_or_read_this_run(self):
        response = await self.client.post("/jobs/1/assessments", headers=self.auth(2), json={"idempotency_key": str(uuid4())})
        self.assertEqual(response.status_code, 404)
        run_id = (await self.start()).json()["id"]
        for path in (f"/assessments/{run_id}", f"/assessments/{run_id}/snapshot",
                     f"/assessments/{run_id}/files", f"/assessments/{run_id}/files/1", "/jobs/1/assessments"):
            with self.subTest(path=path):
                response = await self.client.get(path, headers=self.auth(2))
                self.assertEqual(response.status_code, 404)

    async def test_snapshot_does_not_change_with_draft(self):
        run_id = (await self.start()).json()["id"]
        async with self.sessions.begin() as db:
            job = await db.get(Job, 1)
            job.title = "Changed draft"
            skill = (await db.execute(select(SkillRequirement).where(SkillRequirement.job_id == 1))).scalar_one()
            skill.importance = 1
        response = await self.client.get(f"/assessments/{run_id}/snapshot", headers=self.headers)
        self.assertEqual(response.json()["title"], "Backend developer")
        self.assertEqual(response.json()["skills"][0]["importance"], 5)
        self.assertIn("pdf_limits", response.json())

    async def test_progress_counts_and_excluded_file_privacy(self):
        run_id = (await self.start()).json()["id"]
        claim = await claim_next(self.sessions)
        await save_outcome(self.sessions, claim, discovery("a", "b"))
        claim = await claim_next(self.sessions)
        await save_outcome(self.sessions, claim, Excluded(missing_skills=["Python"]))
        response = await self.client.get(f"/assessments/{run_id}", headers=self.headers)
        self.assertEqual(response.json()["processed_files"], 1)
        self.assertEqual(response.json()["excluded"], 1)
        self.assertEqual(response.json()["total_files"], 2)
        files = (await self.client.get(f"/assessments/{run_id}/files?limit=1", headers=self.headers)).json()
        self.assertEqual(len(files), 1)
        detail = (await self.client.get(f"/assessments/{run_id}/files/{files[0]['id']}", headers=self.headers)).json()
        self.assertEqual(detail["missing_skills"], ["Python"])
        self.assertIsNone(detail["document"])
        claim = await claim_next(self.sessions)
        await save_outcome(self.sessions, claim, Failed(code="invalid_pdf", message="Invalid PDF."))
        done = (await self.client.get(f"/assessments/{run_id}", headers=self.headers)).json()
        self.assertEqual(done["status"], "screened")
        self.assertEqual(done["failed"], 1)
        self.assertEqual(done["processed_files"], 2)
        failed_files = (await self.client.get(f"/assessments/{run_id}/files?status=failed", headers=self.headers)).json()
        self.assertEqual([file["status"] for file in failed_files], ["failed"])
        excluded_files = (await self.client.get(f"/assessments/{run_id}/files?status=excluded", headers=self.headers)).json()
        self.assertEqual([file["status"] for file in excluded_files], ["excluded"])

    async def test_blank_skill_cannot_start(self):
        async with self.sessions.begin() as db:
            skill = (await db.execute(select(SkillRequirement))).scalar_one()
            skill.skill = " "
        self.assertEqual((await self.start()).status_code, 422)

    async def test_missing_skills_cannot_start(self):
        async with self.sessions.begin() as db:
            await db.execute(delete(SkillRequirement).where(SkillRequirement.job_id == 1))
        self.assertEqual((await self.start()).status_code, 422)

    async def test_reusing_key_for_different_job_is_conflict(self):
        key = str(uuid4())
        await self.start(key)
        response = await self.client.post("/jobs/2/assessments", headers=self.headers, json={"idempotency_key": key})
        self.assertEqual(response.status_code, 409)

    async def test_retry_key_after_run_finishes_does_not_restart(self):
        key = str(uuid4())
        first = (await self.start(key)).json()
        claim = await claim_next(self.sessions)
        await save_outcome(self.sessions, claim, Failed(code="no_pdfs", message="No PDFs."))
        repeated = (await self.start(key)).json()
        self.assertEqual(repeated["id"], first["id"])
        self.assertEqual(repeated["status"], "failed")
        self.assertEqual((await self.start()).status_code, 202)
