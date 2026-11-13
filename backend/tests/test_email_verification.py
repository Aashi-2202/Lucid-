import asyncio
from datetime import datetime, timedelta, timezone
import ssl
import unittest
from unittest.mock import patch
from uuid import uuid4

from pydantic import SecretStr
from sqlalchemy import select

from app.core import passwords
from app.core.config import settings
from app.models import Recruiter, EmailVerification
from app.services import verification_email
from test_password_auth import PasswordAccountCase


class EmailVerificationTests(PasswordAccountCase):
    async def begin(self,email="new.user@gmail.com",username="new.user",password="password!"):
        return await self.client.post("/auth/register",json={"username":username,"password":password,"email":email})

    async def verify(self,challenge,code=None):
        return await self.client.post("/auth/register/verify",json={"challenge_id":challenge,"code":code or self.sent[-1][1]})

    async def test_no_session_or_account_before_code_and_single_use_afterwards(self):
        result=await self.begin()
        self.assertEqual(result.status_code,202,result.text)
        self.assertNotIn("token",result.json())
        self.assertNotIn(self.sent[-1][1],result.text)
        challenge=result.json()["challenge_id"]
        self.assertEqual((await self.login("new.user","password!")).status_code,401)
        async with self.sessions() as db:
            pending=await db.get(EmailVerification,challenge)
            self.assertNotEqual(pending.code_digest,self.sent[-1][1])
            self.assertTrue(pending.password_hash.startswith("$argon2id$"))
        verified=await self.verify(challenge)
        self.assertEqual(verified.status_code,201,verified.text)
        self.assertEqual(verified.json()["recruiter"]["email"],"new.user@gmail.com")
        self.assertEqual((await self.verify(challenge)).status_code,400)
        self.assertEqual((await self.login("new.user","password!")).status_code,200)

    async def test_wrong_codes_are_counted_and_expired_codes_fail(self):
        challenge=(await self.begin()).json()["challenge_id"]
        wrong="000000" if self.sent[-1][1]!="000000" else "000001"
        for _ in range(5):
            self.assertEqual((await self.verify(challenge,wrong)).status_code,400)
        self.assertEqual((await self.verify(challenge)).status_code,429)
        async with self.sessions.begin() as db:
            pending=await db.get(EmailVerification,challenge)
            pending.attempts=0;pending.expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
        self.assertEqual((await self.verify(challenge)).status_code,400)

    async def test_resend_cooldown_replaces_code_without_resetting_attempt_budget(self):
        challenge=(await self.begin()).json()["challenge_id"]
        old=self.sent[-1][1]
        self.assertEqual((await self.client.post("/auth/register/resend",json={"challenge_id":challenge})).status_code,429)
        async with self.sessions.begin() as db:
            pending=await db.get(EmailVerification,challenge)
            pending.last_sent_at=datetime.now(timezone.utc)-timedelta(seconds=61)
            pending.attempts=2
        replacement="123456" if old!="123456" else "654321"
        with patch("app.routes.auth.secrets.randbelow",return_value=int(replacement)):
            result=await self.client.post("/auth/register/resend",json={"challenge_id":challenge})
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual((await self.verify(challenge,old)).status_code,400)
        async with self.sessions() as db:
            self.assertEqual((await db.get(EmailVerification,challenge)).attempts,3)
        self.assertEqual((await self.verify(challenge,replacement)).status_code,201)

    async def test_concurrent_verification_creates_only_one_account(self):
        challenge=(await self.begin()).json()["challenge_id"]
        results=await asyncio.gather(self.verify(challenge),self.verify(challenge))
        self.assertEqual(sorted(result.status_code for result in results),[201,400])
        async with self.sessions() as db:
            self.assertEqual(len((await db.scalars(select(Recruiter).where(Recruiter.username=="new.user"))).all()),1)

    async def test_sender_failures_never_create_access_or_expose_private_errors(self):
        with patch("app.services.verification_email.configured",return_value=False):
            result=await self.begin()
            self.assertEqual(result.status_code,503)
        with patch("app.services.verification_email.send_verification",side_effect=verification_email.EmailDeliveryError("Verification email could not be delivered. Please try again later.")):
            result=await self.begin()
        self.assertEqual(result.status_code,503)
        async with self.sessions() as db:
            pending=await db.scalar(select(EmailVerification).where(EmailVerification.username=="new.user"))
            self.assertEqual(pending.delivered,0)
            self.assertIsNone(await db.scalar(select(Recruiter.id).where(Recruiter.username=="new.user")))

    async def test_gmail_required_and_secret_validation_is_redacted(self):
        for email in ("user@example.test","user@gmail.com\r\nBcc:x@other.test","bad@@gmail.com"):
            result=await self.begin(email=email)
            self.assertEqual(result.status_code,422)
            self.assertNotIn(email,result.text)
        result=await self.client.post("/auth/register/verify",json={"challenge_id":str(uuid4()),"code":{"private":"dont-echo-this"}})
        self.assertEqual(result.status_code,422)
        self.assertNotIn("dont-echo-this",result.text)

    async def test_existing_email_cannot_be_taken_or_automatically_merged(self):
        async with self.sessions.begin() as db:
            existing=await db.get(Recruiter,1)
            existing.email="existing@gmail.com"
        result=await self.begin(email="existing@gmail.com")
        self.assertEqual(result.status_code,409)
        self.assertEqual(self.sent,[])

    async def test_legacy_password_account_without_email_keeps_access(self):
        async with self.sessions.begin() as db:
            db.add(Recruiter(username="legacy.user",password_hash=passwords.hash_password("old-password"),name="Legacy",approved=True))
        self.assertEqual((await self.login("legacy.user","old-password")).status_code,200)

    async def test_google_signin_does_not_merge_into_a_verified_username_account(self):
        challenge=(await self.begin()).json()["challenge_id"]
        self.assertEqual((await self.verify(challenge)).status_code,201)
        identity={"sub":"another-google-id","email":"new.user@gmail.com","name":"New","picture":None}
        with patch("app.routes.auth.verify_google_token",return_value=identity):
            result=await self.client.post("/auth/google",json={"credential":"synthetic-token"})
        self.assertEqual(result.status_code,409)
        self.assertIn("username",result.json()["detail"])


class MailTransportTests(unittest.TestCase):
    def test_tls_login_and_message_are_sent_only_to_the_requested_recipient(self):
        for security,transport in (("starttls","SMTP"),("ssl","SMTP_SSL")):
            with patch.object(settings,"smtp_username","sender@gmail.com"),patch.object(settings,"smtp_from_email","sender@gmail.com"),patch.object(settings,"smtp_password",SecretStr("test-app-secret")),patch.object(settings,"smtp_security",security),patch(f"app.services.verification_email.smtplib.{transport}") as smtp:
                client=smtp.return_value.__enter__.return_value
                client.send_message.return_value={}
                verification_email.send_verification("recipient@gmail.com","012345")
                client.login.assert_called_once_with("sender@gmail.com","test-app-secret")
                message=client.send_message.call_args.args[0]
                self.assertEqual(str(message["To"]),"recipient@gmail.com")
                self.assertIn("012345",message.get_content())
                context=client.starttls.call_args.kwargs["context"] if security=="starttls" else smtp.call_args.kwargs["context"]
                self.assertTrue(context.check_hostname)
                self.assertEqual(context.verify_mode,ssl.CERT_REQUIRED)

    def test_smtp_failure_is_redacted(self):
        with patch.object(settings,"smtp_username","sender@gmail.com"),patch.object(settings,"smtp_password",SecretStr("private-password")),patch("app.services.verification_email.smtplib.SMTP",side_effect=OSError("private-password")):
            with self.assertRaises(verification_email.EmailDeliveryError) as caught:
                verification_email.send_verification("recipient@gmail.com","123456")
            self.assertNotIn("private-password",str(caught.exception))
