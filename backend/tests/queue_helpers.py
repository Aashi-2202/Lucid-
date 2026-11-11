"""Real on-disk test database, isolated from Neon and developer credentials."""

import tempfile
import unittest
from uuid import uuid4

from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.core.database import Base
from app.models import Assessment, Job, Recruiter, SkillRequirement
from app.schemas.assessments import IntakeSnapshot, SkillSnapshot, SourceFile, Discovered


def snapshot():
    return IntakeSnapshot(
        title="Backend developer", description="Build reporting services", company=None,
        folder_id="job_folder", folder_link="https://drive.google.com/drive/folders/job_folder",
        skills=[SkillSnapshot(skill="Python", mandatory=True, importance=5, required_evidence_level=3,
                              assessment_method="resume", aliases=["Python3"])],
        max_files=100, file_timeout_seconds=60, embedding_model="all-MiniLM-L6-v2",
        relevance_thresholds=[0.30, 0.50, 0.65, 0.80],
    )


def discovery(*ids):
    return Discovered(files=[SourceFile(id=file_id, name=f"{file_id}.pdf", version="3", size="1024") for file_id in ids])


class QueueTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="lucid-queue-tests-")
        self.url = "sqlite+aiosqlite:///" + self.temp.name.replace("\\", "/") + "/queue.db"
        self.open_engine()
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with self.sessions.begin() as db:
            db.add_all([
                Recruiter(id=1, google_id="one", email="one@example.test", name="One", approved=True),
                Recruiter(id=2, google_id="two", email="two@example.test", name="Two", approved=True),
                Recruiter(id=3, google_id="three", email="three@example.test", name="Three", approved=False),
            ])
            await db.flush()
            db.add(Job(id=1, recruiter_id=1, title="Backend developer", description="Build reporting services",
                       folder_link="https://drive.google.com/drive/folders/job_folder", folder_id="job_folder"))
            db.add(Job(id=2, recruiter_id=2, title="Other job", description="Another job",
                       folder_link="https://drive.google.com/drive/folders/other_folder", folder_id="other_folder"))
            await db.flush()
            db.add(SkillRequirement(job_id=1, skill="Python", mandatory=True, importance=5,
                                    required_evidence_level=3, assessment_method="resume", aliases=["Python3"]))

    def open_engine(self):
        self.engine = create_async_engine(self.url)

        @event.listens_for(self.engine.sync_engine, "connect")
        def foreign_keys(connection, _):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()
        self.temp.cleanup()

    async def enqueue(self):
        run_id = str(uuid4())
        async with self.sessions.begin() as db:
            db.add(Assessment(id=run_id, job_id=1, recruiter_id=1,
                              idempotency_key=str(uuid4()), snapshot=snapshot().model_dump(mode="json")))
        return run_id
