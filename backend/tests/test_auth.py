"""Authentication boundary tests; Google signature verification stays in Google's library."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import httpx
import jwt
from google.auth.exceptions import TransportError
from sqlalchemy import select

from app.core.auth import AuthError, create_session_token, decode_session_token, verify_google_token
from app.core.config import settings
from app.core.database import get_db
from app.main import app
from app.models import Recruiter
from queue_helpers import QueueTestCase


class TokenTests(unittest.TestCase):
    def setUp(self):
        self.secret = patch.object(settings, "jwt_secret", "auth-test-secret-" * 5)
        self.secret.start()
        self.addCleanup(self.secret.stop)

    def test_session_roundtrip(self):
        self.assertEqual(decode_session_token(create_session_token(7, "a@example.test"))["sub"], "7")

    def test_session_requires_expiry_and_numeric_positive_subject(self):
        now = datetime.now(timezone.utc)
        for payload in (
            {"sub": "1", "iat": now},
            {"sub": "bad", "iat": now, "exp": now + timedelta(minutes=1)},
            {"sub": "0", "iat": now, "exp": now + timedelta(minutes=1)},
            {"sub": "1", "iat": now - timedelta(hours=2), "exp": now - timedelta(hours=1)},
        ):
            with self.subTest(payload=payload), self.assertRaises(AuthError):
                decode_session_token(jwt.encode(payload, settings.jwt_secret, algorithm="HS256"))

    def test_google_requires_configuration(self):
        with patch.object(settings, "google_client_id", ""), self.assertRaises(AuthError) as caught:
            verify_google_token("bad")
        self.assertEqual(caught.exception.status_code, 503)

    def test_google_checks_verified_email_issuer_and_subject(self):
        valid = {"iss": "https://accounts.google.com", "sub": "google-user", "email": "a@example.test", "email_verified": True}
        with patch.object(settings, "google_client_id", "test-client"), patch("app.core.auth.google_id_token.verify_oauth2_token") as verify:
            verify.return_value = valid
            self.assertEqual(verify_google_token("credential"), valid)
            self.assertEqual(verify.call_args.args[2], "test-client")
            for changes in ({"email_verified": False}, {"email": ""}, {"iss": "other"}, {"sub": ""}):
                verify.return_value = {**valid, **changes}
                with self.subTest(changes=changes), self.assertRaises(AuthError):
                    verify_google_token("credential")

    def test_google_failures_are_safe_and_retryable_when_transport_fails(self):
        with patch.object(settings, "google_client_id", "test-client"), patch("app.core.auth.google_id_token.verify_oauth2_token") as verify:
            for failure, status in ((ValueError("private-detail"), 401), (TransportError("private-detail"), 503)):
                verify.side_effect = failure
                with self.assertRaises(AuthError) as caught:
                    verify_google_token("credential")
                self.assertEqual(caught.exception.status_code, status)
                self.assertNotIn("private-detail", caught.exception.message)


class SignInTests(QueueTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        async def test_db():
            async with self.sessions() as db:
                yield db
        app.dependency_overrides[get_db] = test_db
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
        self.secret = patch.object(settings, "jwt_secret", "auth-test-secret-" * 5)
        self.secret.start()
        self.signup = patch.object(settings, "allow_public_signup", False)
        self.signup.start()

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.clear()
        self.secret.stop()
        self.signup.stop()
        await super().asyncTearDown()

    async def sign_in(self, email="allowed@example.test", sub="new-google-user"):
        with patch("app.routes.auth.verify_google_token", return_value={"sub": sub, "email": email, "name": "Recruiter"}):
            return await self.client.post("/auth/google", json={"credential": "verified-by-test"})

    async def test_allowlisted_first_login_gets_session_and_profile(self):
        with patch.object(settings, "approved_recruiter_emails", [" ALLOWED@example.test "]):
            response = await self.sign_in()
        self.assertEqual(response.status_code, 200, response.text)
        token = response.json()["token"]
        me = await self.client.get("/auth/me", headers={"Authorization": "Bearer " + token})
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["email"], "allowed@example.test")
        repeat = await self.sign_in()
        self.assertEqual(repeat.json()["recruiter"]["id"], me.json()["id"])

    async def test_unlisted_account_stays_pending(self):
        with patch.object(settings, "approved_recruiter_emails", ["different@example.test"]):
            response = await self.sign_in()
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("token", response.json())
        async with self.sessions() as db:
            account = (await db.execute(select(Recruiter).where(Recruiter.google_id == "new-google-user"))).scalar_one()
            self.assertFalse(account.approved)

    async def test_public_signup_registers_unlisted_account_and_preserves_identity(self):
        with patch.object(settings, "allow_public_signup", True), patch.object(settings, "approved_recruiter_emails", []):
            response = await self.sign_in()
            self.assertEqual(response.status_code, 200, response.text)
            repeat = await self.sign_in()
        self.assertEqual(repeat.json()["recruiter"]["id"], response.json()["recruiter"]["id"])
        headers = {"Authorization": "Bearer " + response.json()["token"]}
        self.assertEqual((await self.client.get("/auth/me", headers=headers)).status_code, 200)
        self.assertEqual((await self.client.get("/jobs", headers=headers)).json(), [])
        self.assertEqual((await self.client.get("/jobs/1", headers=headers)).status_code, 403)

    async def test_public_signup_approves_existing_pending_account_on_verified_login(self):
        with patch.object(settings, "allow_public_signup", True):
            response = await self.sign_in("three@example.test", "three")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["recruiter"]["id"], 3)
        async with self.sessions() as db:
            self.assertTrue((await db.get(Recruiter, 3)).approved)

    async def test_public_signup_does_not_approve_pending_account_with_invalid_token(self):
        with patch.object(settings, "allow_public_signup", True), patch("app.routes.auth.verify_google_token", side_effect=AuthError("Invalid token")):
            response = await self.client.post("/auth/google", json={"credential": "invalid"})
        self.assertEqual(response.status_code, 401)
        async with self.sessions() as db:
            self.assertFalse((await db.get(Recruiter, 3)).approved)
            self.assertEqual(len((await db.execute(select(Recruiter))).scalars().all()), 3)

    async def test_existing_unapproved_account_is_not_silently_reapproved(self):
        with patch.object(settings, "approved_recruiter_emails", ["three@example.test"]):
            response = await self.sign_in("three@example.test", "three")
        self.assertEqual(response.status_code, 403)

    async def test_invalid_google_token_cannot_register_an_account(self):
        with patch("app.routes.auth.verify_google_token", side_effect=AuthError("Invalid token")):
            response = await self.client.post("/auth/google", json={"credential": "invalid"})
        self.assertEqual(response.status_code, 401)
        async with self.sessions() as db:
            self.assertEqual(len((await db.execute(select(Recruiter))).scalars().all()), 3)
