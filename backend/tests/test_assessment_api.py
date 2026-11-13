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
        async with self.sessions.begin() as db:
            job = await db.get(Job, 1)
            job.additional_competencies = ["Communication"]
        run_id = (await self.start()).json()["id"]
        async with self.sessions.begin() as db:
            job = await db.get(Job, 1)
            job.title = "Changed draft"
            job.additional_competencies = ["Learning Agility"]
            skill = (await db.execute(select(SkillRequirement).where(SkillRequirement.job_id == 1))).scalar_one()
            skill.importance = 1
        response = await self.client.get(f"/assessments/{run_id}/snapshot", headers=self.headers)
        self.assertEqual(response.json()["title"], "Backend developer")
        self.assertEqual(response.json()["skills"][0]["importance"], 5)
        self.assertIn("pdf_limits", response.json())
        self.assertEqual(response.json()["analysis_version"], "resume-evidence-v2")
        self.assertEqual(response.json()["summary_version"], "job-match-summary-v1")
        self.assertEqual(response.json()["additional_competencies"], ["Communication"])

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
        self.assertEqual(done["status"], "completed")
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

    async def test_completed_analysis_results_preserve_ties_and_scope(self):
        from app.schemas.assessments import Ready
        from app.services.analysis import analyse
        from test_analysis import document, exact_encoder, snapshot
        run_id=(await self.start()).json()["id"]
        claim=await claim_next(self.sessions)
        await save_outcome(self.sessions,claim,discovery("a","b","c"))
        for _ in range(2):
            claim=await claim_next(self.sessions)
            doc=document("Projects\nBuilt Python services.")
            doc=doc.model_copy(update={"analysis":analyse(doc,snapshot().model_copy(update={"analysis_version":"resume-evidence-v2"}),encoder=exact_encoder)})
            await save_outcome(self.sessions,claim,Ready(document=doc))
        claim=await claim_next(self.sessions)
        await save_outcome(self.sessions,claim,Excluded(missing_skills=["Python"]))
        progress=(await self.client.get(f"/assessments/{run_id}",headers=self.headers)).json()
        self.assertEqual(progress["status"],"completed")
        self.assertEqual(progress["assessed"],2)
        result=await self.client.get(f"/assessments/{run_id}/results",headers=self.headers)
        self.assertEqual(result.status_code,200)
        rows=result.json()["rows"]
        self.assertFalse(result.json()["provisional"])
        self.assertEqual([row["rank"] for row in rows],[1,1])
        self.assertEqual([row["score"] for row in rows],[75,75])
        other=await self.client.get(f"/assessments/{run_id}/results",headers=self.auth(2))
        self.assertEqual(other.status_code,404)
        async with self.sessions.begin() as db:
            job=await db.get(Job,1)
            job.title="Renamed after assessment"
        export=await self.client.get(f"/assessments/{run_id}/export",headers=self.headers)
        self.assertEqual(export.status_code,200)
        self.assertIn('filename="Backend developer-results.csv"',export.headers["Content-Disposition"])
        self.assertIn("filename*=UTF-8''Backend%20developer-results.csv",export.headers["Content-Disposition"])
        self.assertEqual(len(export.text.splitlines()),3)
        detail=(await self.client.get(f"/assessments/{run_id}/files/{rows[0]['file_id']}",headers=self.headers)).json()
        self.assertEqual(detail["document"]["analysis"]["skills"][0]["evidence_level"],3)

    async def test_active_export_is_blocked_and_rankings_are_provisional(self):
        run_id=(await self.start()).json()["id"]
        response=await self.client.get(f"/assessments/{run_id}/export",headers=self.headers)
        self.assertEqual(response.status_code,409)
        result=await self.client.get(f"/assessments/{run_id}/results",headers=self.headers)
        self.assertTrue(result.json()["provisional"])

    async def test_csv_escapes_formula_filenames(self):
        from app.routes.assessments import csv_cell
        self.assertEqual(csv_cell("=HYPERLINK(test)"),"'=HYPERLINK(test)")
        self.assertEqual(csv_cell("   +test"),"'   +test")
        self.assertEqual(csv_cell("resume.pdf"),"resume.pdf")

    async def test_summary_is_saved_exposed_and_exported_without_quotes(self):
        import csv
        import io
        from app.schemas.assessments import Ready
        from app.services.analysis import analyse
        from test_analysis import document, exact_encoder
        async with self.sessions.begin() as db:
            job=await db.get(Job,1)
            job.additional_competencies=["Communication","Learning Agility"]
        run_id=(await self.start()).json()["id"]
        claim=await claim_next(self.sessions)
        await save_outcome(self.sessions,claim,discovery("a"))
        claim=await claim_next(self.sessions)
        quote="Presented quarterly forecasting findings to client stakeholders in weekly reviews."
        doc=document("Projects\nBuilt Python reporting services. "+quote)
        analysis=analyse(doc,claim.request.snapshot,encoder=exact_encoder)
        await save_outcome(self.sessions,claim,Ready(document=doc.model_copy(update={"analysis":analysis})))
        results=(await self.client.get(f"/assessments/{run_id}/results",headers=self.headers)).json()
        row=results["rows"][0]
        self.assertIn("Communication:",row["job_match_summary"])
        self.assertNotIn(quote,row["job_match_summary"])
        exported=await self.client.get(f"/assessments/{run_id}/export",headers=self.headers)
        records=list(csv.DictReader(io.StringIO(exported.text)))
        self.assertEqual(records[0]["Job Match Summary"],row["job_match_summary"])
        self.assertIn("Python:",records[0]["Job Match Summary"])
        self.assertIn("Learning Agility: Not evidenced",records[0]["Job Match Summary"])
        detail=(await self.client.get(f"/assessments/{run_id}/files/{row['file_id']}",headers=self.headers)).json()
        self.assertEqual(detail["document"]["analysis"]["additional_competencies"][0]["status"],"supporting_activity")

    async def test_terminal_undetermined_evidence_stays_provisional(self):
        from app.schemas.assessments import Ready
        from app.services.analysis import analyse
        from test_analysis import document
        configured=await self.client.patch('/jobs/1',headers=self.headers,json={"skills":[
            {"skill":"Python","mandatory":True,"importance":3,"required_evidence_level":3},
            {"skill":"SQL","mandatory":False,"importance":3,"required_evidence_level":3}]})
        self.assertEqual(configured.status_code,200)
        run_id=(await self.start()).json()["id"]
        claim=await claim_next(self.sessions)
        await save_outcome(self.sessions,claim,discovery("a"))
        claim=await claim_next(self.sessions)
        doc=document("Projects\nDeveloped Python server endpoints with FastAPI.")
        doc=doc.model_copy(update={"analysis":analyse(doc,claim.request.snapshot,encoder=lambda texts:[[1.,0.],[1.,0.],[.9,(1-.9**2)**.5]])})
        await save_outcome(self.sessions,claim,Ready(document=doc))
        result=(await self.client.get(f"/assessments/{run_id}/results",headers=self.headers)).json()
        self.assertTrue(result["provisional"])
        self.assertFalse(result["rows"][0]["complete"])
        self.assertEqual(result["rows"][0]["score"],50)

    async def test_old_intake_run_does_not_claim_ranked_results(self):
        run_id=await self.enqueue()
        claim=await claim_next(self.sessions)
        await save_outcome(self.sessions,claim,discovery("a"))
        claim=await claim_next(self.sessions)
        from app.schemas.assessments import Ready
        from test_analysis import document
        await save_outcome(self.sessions,claim,Ready(document=document("Skills\nPython")))
        run=(await self.client.get(f"/assessments/{run_id}",headers=self.headers)).json()
        self.assertEqual(run["status"],"screened")
        self.assertEqual(run["assessed"],0)
        results=(await self.client.get(f"/assessments/{run_id}/results",headers=self.headers)).json()
        self.assertEqual(results["rows"],[])
