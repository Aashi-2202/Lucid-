import tempfile
import unittest
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.migrate import upgrade_connection


class AccountMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_accounts_and_job_foreign_keys_survive_idempotent_upgrade(self):
        with tempfile.TemporaryDirectory() as directory:
            url = "sqlite+aiosqlite:///" + (Path(directory) / "legacy.db").as_posix()
            engine = create_async_engine(url)
            try:
                async with engine.begin() as conn:
                    await conn.execute(text('''CREATE TABLE recruiters (
                        id INTEGER PRIMARY KEY, google_id VARCHAR(255) NOT NULL UNIQUE,
                        email VARCHAR(255) NOT NULL UNIQUE, name VARCHAR(255) NOT NULL,
                        picture VARCHAR(1024), approved BOOLEAN NOT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        last_login DATETIME DEFAULT CURRENT_TIMESTAMP)'''))
                    await conn.execute(text("INSERT INTO recruiters (id, google_id, email, name, approved) VALUES (1, 'existing-google', 'existing@example.test', 'Existing recruiter', 1)"))
                    await conn.run_sync(upgrade_connection)
                    await conn.execute(text("INSERT INTO jobs (id, recruiter_id, title, description, folder_link, folder_id, status) VALUES (1, 1, 'Existing job', 'Keep it', 'synthetic_folder', 'synthetic_folder', 'draft')"))
                    await conn.run_sync(upgrade_connection)
                    original = (await conn.execute(text("SELECT google_id, email, username, password_hash FROM recruiters WHERE id=1"))).one()
                    self.assertEqual(tuple(original), ("existing-google", "existing@example.test", None, None))
                    self.assertEqual(await conn.scalar(text("SELECT recruiter_id FROM jobs WHERE id=1")), 1)
                    columns = await conn.run_sync(lambda connection: {c["name"]:c for c in inspect(connection).get_columns("recruiters")})
                    self.assertTrue(columns["google_id"]["nullable"])
                    self.assertTrue(columns["email"]["nullable"])
                    await conn.execute(text("INSERT INTO recruiters (name, username, password_hash, approved) VALUES ('Local', 'local.user', 'fixture-hash', 1)"))
                    self.assertEqual(await conn.scalar(text("SELECT version_num FROM alembic_version")), "0001_password_accounts")
                    self.assertEqual((await conn.execute(text("PRAGMA foreign_key_check"))).all(), [])
            finally:
                await engine.dispose()
