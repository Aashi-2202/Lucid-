import asyncio
import unittest
from unittest.mock import patch

import httpx
from sqlalchemy import select

from app.core import passwords
from app.core.auth import create_session_token, decode_session_token
from app.core.config import settings
from app.core.database import get_db
from app.main import app
from app.models import Recruiter
from queue_helpers import QueueTestCase

PASSWORD = "correct horse battery staple"


class PasswordAccountsTests(QueueTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        async def test_db():
            async with self.sessions() as db:
                yield db
        app.dependency_overrides[get_db] = test_db
        self.patches = [patch.object(settings, "allow_public_signup", True),
                        patch.object(settings, "jwt_secret", "test-password-session-" * 5),
                        patch.object(passwords, "throttle", passwords.AuthThrottle())]
        for item in self.patches:
            item.start()
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.clear()
        for item in reversed(self.patches):
            item.stop()
        await super().asyncTearDown()

    async def register(self, username="recruiter.local", password=PASSWORD):
        return await self.client.post("/auth/register", json={"username": username, "password": password})

    async def login(self, username="recruiter.local", password=PASSWORD):
        return await self.client.post("/auth/password", json={"username": username, "password": password})

    async def test_register_login_and_use_owned_job_without_google_or_email(self):
        created = await self.register(" Recruiter.Local ")
        self.assertEqual(created.status_code, 201, created.text)
        info = created.json()["recruiter"]
        self.assertEqual(info["username"], "recruiter.local")
        self.assertIsNone(info["email"])
        self.assertNotIn("password", created.text)
        token = created.json()["token"]
        self.assertEqual(decode_session_token(token)["sub"], str(info["id"]))
        async with self.sessions() as db:
            account = await db.get(Recruiter, info["id"])
            self.assertIsNone(account.google_id)
            self.assertTrue(account.password_hash.startswith("$argon2id$"))
            self.assertNotIn(PASSWORD, account.password_hash)
        login = await self.login("RECRUITER.LOCAL")
        self.assertEqual(login.status_code, 200, login.text)
        headers = {"Authorization": "Bearer " + login.json()["token"]}
        self.assertEqual((await self.client.get("/auth/me", headers=headers)).json()["id"], info["id"])
        self.assertEqual((await self.client.get("/jobs", headers=headers)).json(), [])
        self.assertEqual((await self.client.get("/jobs/1", headers=headers)).status_code, 403)
        job = await self.client.post("/jobs", headers=headers, json={"title":"Local recruiter job", "description":"Build APIs",
            "folder_link":"https://drive.google.com/drive/folders/synthetic_folder", "skills":[{"skill":"Python"}]})
        self.assertEqual(job.status_code, 201, job.text)
        self.assertIsNone(job.json()["recruiter_email"])
        self.assertEqual((await self.client.delete(f'/jobs/{job.json()["id"]}', headers=headers)).status_code, 204)

    async def test_duplicate_and_concurrent_case_variants_do_not_create_extra_accounts(self):
        responses = await asyncio.gather(self.register("New.User"), self.register("new.user"))
        self.assertEqual(sorted(r.status_code for r in responses), [201, 409], [r.text for r in responses])
        async with self.sessions() as db:
            accounts = (await db.execute(select(Recruiter).where(Recruiter.username == "new.user"))).scalars().all()
            self.assertEqual(len(accounts), 1)
        self.assertEqual((await self.login("NEW.USER")).status_code, 200)

    async def test_wrong_unknown_and_google_only_users_get_same_failure(self):
        self.assertEqual((await self.register()).status_code, 201)
        for username in ("recruiter.local", "unknown.user", "one"):
            response = await self.login(username, "incorrect-password")
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json()["detail"], "Incorrect username or password.")
            self.assertNotIn("token", response.json())

    async def test_validation_never_echoes_password_and_does_not_create_account(self):
        cases = [("valid.user", "too-short"), ("valid.user", "private-" * 20),
                 ("bad@username", PASSWORD), ("xx", PASSWORD), ("valid.user", ""), ("valid.user", " " * 12)]
        for username, password in cases:
            response = await self.register(username, password)
            self.assertEqual(response.status_code, 422, response.text)
            if password:
                self.assertNotIn(password, response.text)
        response = await self.client.post("/auth/register", json={"username":"valid.user", "password":{"private":"do-not-echo"}})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn("do-not-echo", response.text)
        async with self.sessions() as db:
            self.assertEqual(len((await db.execute(select(Recruiter))).scalars().all()), 3)

    async def test_password_spaces_and_unicode_are_preserved(self):
        secret = "  café passphrase 🍀  "
        self.assertEqual((await self.register(password=secret)).status_code, 201)
        self.assertEqual((await self.login(password=secret.strip())).status_code, 401)
        self.assertEqual((await self.login(password=secret)).status_code, 200)

    async def test_pending_account_needs_correct_password_before_public_promotion(self):
        with patch.object(settings, "allow_public_signup", False):
            self.assertEqual((await self.register()).status_code, 403)
            self.assertEqual((await self.login()).status_code, 403)
        self.assertEqual((await self.login(password="wrong-password")).status_code, 401)
        async with self.sessions() as db:
            account = await db.scalar(select(Recruiter).where(Recruiter.username == "recruiter.local"))
            self.assertFalse(account.approved)
        self.assertEqual((await self.login()).status_code, 200)

    async def test_existing_google_identity_and_owned_jobs_are_preserved(self):
        await self.register("one")
        token = create_session_token(1, "one@example.test")
        headers = {"Authorization": "Bearer " + token}
        info = (await self.client.get("/auth/me", headers=headers)).json()
        self.assertEqual(info["email"], "one@example.test")
        self.assertIsNone(info["username"])
        self.assertEqual([job["id"] for job in (await self.client.get("/jobs", headers=headers)).json()], [1])

    async def test_login_and_registration_rate_limits(self):
        for _ in range(10):
            self.assertEqual((await self.login("unknown.user")).status_code, 401)
        blocked = await self.login("unknown.user")
        self.assertEqual(blocked.status_code, 429)
        self.assertIn("Retry-After", blocked.headers)
        # A spoofed forwarding header cannot reset the resolved-peer bucket.
        for i in range(10):
            self.assertEqual((await self.register(f"user{i}")).status_code, 201)
        blocked = await self.client.post("/auth/register", headers={"X-Forwarded-For":"198.51.100.1"}, json={"username":"another.user","password":PASSWORD})
        self.assertEqual(blocked.status_code, 429)


class PasswordUtilityTests(unittest.TestCase):
    def test_hashes_are_salted_and_wrong_passwords_do_not_match(self):
        first, second = passwords.hash_password(PASSWORD), passwords.hash_password(PASSWORD)
        self.assertNotEqual(first, second)
        self.assertTrue(passwords.verify_password(first, PASSWORD)[0])
        self.assertFalse(passwords.verify_password(first, "wrong")[0])
        self.assertFalse(passwords.verify_password(None, "dummy-account-comparison-only")[0])
        self.assertFalse(passwords.verify_password("invalid-hash", PASSWORD)[0])

    def test_rate_limit_expires_and_rejects_without_unbounded_memory(self):
        now = [100.0]
        limiter = passwords.AuthThrottle(clock=lambda:now[0])
        limiter.check("login", "peer", 1, 300)
        with self.assertRaises(Exception) as caught:
            limiter.check("login", "peer", 1, 300)
        self.assertEqual(caught.exception.status_code, 429)
        now[0] += 301
        limiter.check("login", "peer", 1, 300)
        self.assertEqual(len(limiter.windows), 1)
        limiter.windows = {("login", str(i)): (now[0] + 300, 1) for i in range(4096)}
        with self.assertRaises(Exception) as caught:
            limiter.check("login", "new-peer", 30, 300)
        self.assertEqual(caught.exception.status_code, 429)
        self.assertEqual(len(limiter.windows), 4096)
