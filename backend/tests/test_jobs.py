import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx
from sqlalchemy import null, select

from app.core.auth import create_session_token
from app.core.database import get_db
from app.main import app
from app.models import Assessment, AssessmentFile, Job, SkillRequirement
from queue_helpers import QueueTestCase


def requirement(**changes):
    return {"skill": "Python", "description": "Build reporting pipelines", "mandatory": True,
            "importance": 5, "required_evidence_level": 3, "assessment_method": "resume",
            "aliases": ["Python3", "Python 3"], **changes}


class JobConfigurationTests(QueueTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        async def test_db():
            async with self.sessions() as db:
                yield db
        app.dependency_overrides[get_db] = test_db
        self.secret = patch("app.core.config.settings.jwt_secret", "test-secret-" * 8)
        self.secret.start()
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test",
            headers={"Authorization": "Bearer " + create_session_token(1, "one@example.test")})

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.clear()
        self.secret.stop()
        await super().asyncTearDown()

    async def create(self, skills):
        return await self.client.post("/jobs", json={"title":"Data engineer", "description":"Build pipelines",
            "folder_link":"https://drive.google.com/drive/folders/test_folder", "skills":skills})

    async def test_create_and_reopen_preserves_all_seven_settings(self):
        skills = [requirement(), requirement(skill="Communication", assessment_method="interview", mandatory=False, aliases=[])]
        created = await self.create(skills)
        self.assertEqual(created.status_code, 201, created.text)
        reopened = await self.client.get('/jobs/' + str(created.json()["id"]))
        self.assertEqual(reopened.status_code, 200)
        actual = [{key:value for key,value in skill.items() if key != "id"} for skill in reopened.json()["skills"]]
        self.assertEqual(actual, skills)

    async def test_update_saves_job_and_skills_together_and_clears_company(self):
        response = await self.client.patch("/jobs/1", json={"title":"Revised", "company":None,
            "skills":[requirement(skill="SQL", mandatory=False, importance=2, required_evidence_level=5, aliases=["PostgreSQL"])]})
        self.assertEqual(response.status_code, 200, response.text)
        reopened = (await self.client.get("/jobs/1")).json()
        self.assertEqual(reopened["title"], "Revised")
        self.assertIsNone(reopened["company"])
        self.assertEqual(len(reopened["skills"]), 1)
        self.assertEqual(reopened["skills"][0]["skill"], "SQL")
        self.assertEqual(reopened["skills"][0]["required_evidence_level"], 5)

    async def test_invalid_requirement_does_not_partially_save_job(self):
        response = await self.client.patch("/jobs/1", json={"title":"Must not save", "skills":[requirement(importance=6)]})
        self.assertEqual(response.status_code, 422)
        reopened = (await self.client.get("/jobs/1")).json()
        self.assertEqual(reopened["title"], "Backend developer")
        self.assertEqual(reopened["skills"][0]["skill"], "Python")
        self.assertEqual((await self.create([requirement(skill="   ")])).status_code, 422)
        async with self.sessions() as db:
            self.assertEqual(len((await db.execute(select(Job))).scalars().all()), 2)

    async def test_aliases_normalize_without_generating_unapproved_alternatives(self):
        response = await self.create([requirement(skill=" Python ", aliases=[" Python3 ", "python3", "", "Python 3"])])
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["skills"][0]["aliases"], ["Python3", "Python 3"])
        self.assertEqual(response.json()["skills"][0]["skill"], "Python")

    async def test_other_recruiter_cannot_replace_requirements(self):
        response = await self.client.patch("/jobs/2", json={"skills":[requirement()]})
        self.assertEqual(response.status_code, 403)

    async def test_competencies_save_reopen_clear_and_remain_separate_from_skills(self):
        response = await self.client.post("/jobs", json={"title":"Role", "description":"Work", "folder_link":"test_folder_12345678901234567890", "skills":[requirement()],
            "additional_competencies":[" Communication ","communication","Learning Agility"]})
        self.assertEqual(response.status_code,201,response.text)
        job_id=response.json()["id"]
        reopened=(await self.client.get(f"/jobs/{job_id}")).json()
        self.assertEqual(reopened["additional_competencies"],["Communication","Learning Agility"])
        self.assertEqual(len(reopened["skills"]),1)
        unchanged=await self.client.patch(f"/jobs/{job_id}",json={"title":"Renamed"})
        self.assertEqual(unchanged.json()["additional_competencies"],reopened["additional_competencies"])
        cleared=await self.client.patch(f"/jobs/{job_id}",json={"additional_competencies":[]})
        self.assertEqual(cleared.json()["additional_competencies"],[])

    async def test_competency_validation_and_ownership_do_not_allow_partial_saves(self):
        for values in ([" "],["DSA"],["x"*101],[str(i) for i in range(21)]):
            response=await self.client.patch("/jobs/1",json={"title":"Must not save","additional_competencies":values})
            self.assertEqual(response.status_code,422,response.text)
        original=(await self.client.get("/jobs/1")).json()
        self.assertEqual(original["title"],"Backend developer")
        self.assertEqual(original["additional_competencies"],[])
        self.assertEqual((await self.client.patch("/jobs/2",json={"additional_competencies":["Communication"]})).status_code,403)

    async def test_non_draft_jobs_cannot_be_reconfigured(self):
        async with self.sessions.begin() as db:
            job = await db.get(Job, 1)
            job.status = "active"
        response = await self.client.patch("/jobs/1", json={"skills":[requirement()]})
        self.assertEqual(response.status_code, 400)

    async def test_legacy_skill_endpoint_and_empty_list_still_work(self):
        response = await self.client.put("/jobs/1/skills", json=[requirement(importance=4)])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()[0]["importance"], 4)
        response = await self.client.patch("/jobs/1", json={"skills":[]})
        self.assertEqual(response.json()["skills"], [])

    async def test_unchanged_folder_keeps_verified_metadata(self):
        async with self.sessions.begin() as db:
            job = await db.get(Job, 1)
            job.folder_name = "Verified folder"
            job.folder_pdf_count = 5
        response = await self.client.patch("/jobs/1", json={"folder_link":"https://drive.google.com/drive/folders/job_folder", "skills":[requirement()]})
        self.assertEqual(response.json()["folder_name"], "Verified folder")
        changed = await self.client.patch("/jobs/1", json={"folder_link":"https://drive.google.com/drive/folders/different_folder"})
        self.assertIsNone(changed.json()["folder_name"])
        self.assertIsNone(changed.json()["folder_pdf_count"])

    async def terminal_run(self, status="screened"):
        run_id = str(uuid4())
        async with self.sessions.begin() as db:
            db.add(Assessment(id=run_id, job_id=1, recruiter_id=1,
                idempotency_key=str(uuid4()), status=status, active_slot=null(),
                snapshot={"analysis_version": "resume-evidence-v1"}))
            await db.flush()
            db.add(AssessmentFile(assessment_id=run_id, position=0, drive_file_id="synthetic-file",
                name="synthetic.pdf", version="1", source_metadata={}, status="ready_for_analysis",
                document={"analysis": {"score": 50}}))
        return run_id

    async def test_delete_executed_job_removes_all_saved_results_and_requirements(self):
        run_ids = [await self.terminal_run(), await self.terminal_run("failed")]
        with patch("app.routes.jobs.check_folder_access") as drive:
            response = await self.client.delete("/jobs/1")
        self.assertEqual(response.status_code, 204, response.text)
        self.assertEqual(response.content, b"")
        drive.assert_not_called()
        self.assertEqual([job["id"] for job in (await self.client.get("/jobs")).json()], [])
        for run_id in run_ids:
            self.assertEqual((await self.client.get(f"/assessments/{run_id}")).status_code, 404)
        async with self.sessions() as db:
            self.assertIsNone(await db.get(Job, 1))
            self.assertIsNotNone(await db.get(Job, 2))
            self.assertEqual((await db.execute(select(SkillRequirement))).scalars().all(), [])
            self.assertEqual((await db.execute(select(Assessment))).scalars().all(), [])
            self.assertEqual((await db.execute(select(AssessmentFile))).scalars().all(), [])

    async def test_delete_without_assessments_and_missing_job(self):
        self.assertEqual((await self.client.delete("/jobs/1")).status_code, 204)
        self.assertEqual((await self.client.delete("/jobs/1")).status_code, 404)

    async def test_delete_requires_approved_owner(self):
        self.assertEqual((await self.client.delete("/jobs/2")).status_code, 404)
        for headers in ({"Authorization": ""}, {"Authorization": "Bearer " + create_session_token(3, "three@example.test")}):
            response = await self.client.delete("/jobs/1", headers=headers)
            self.assertIn(response.status_code, (401, 403))
        async with self.sessions() as db:
            self.assertIsNotNone(await db.get(Job, 1))
            self.assertIsNotNone(await db.get(Job, 2))

    async def test_delete_blocks_queued_and_running_assessment_without_removing_history(self):
        await self.terminal_run()
        run_id = await self.enqueue()
        for state in ("queued", "running"):
            async with self.sessions.begin() as db:
                (await db.get(Assessment, run_id)).status = state
            response = await self.client.delete("/jobs/1")
            self.assertEqual(response.status_code, 409, response.text)
            async with self.sessions() as db:
                self.assertIsNotNone(await db.get(Job, 1))
                self.assertEqual(len((await db.execute(select(Assessment))).scalars().all()), 2)
                self.assertEqual(len((await db.execute(select(AssessmentFile))).scalars().all()), 1)
                self.assertEqual(len((await db.execute(select(SkillRequirement))).scalars().all()), 1)
