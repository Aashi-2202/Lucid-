"""Authentication routes — Google Sign-In and session management."""

import asyncio
from datetime import datetime, timezone, timedelta
import hashlib
import hmac
import re
import secrets
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, SecretStr, field_validator
from sqlalchemy import select, delete, update, or_, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthError, create_session_token, verify_google_token
from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_recruiter
from app.core import passwords
from app.models.recruiter import Recruiter
from app.models.email_verification import EmailVerification
from app.services import verification_email

router = APIRouter(prefix="/auth", tags=["auth"])


class GoogleSignInRequest(BaseModel):
    """Request body for Google Sign-In."""
    credential: str  # The ID token from Google Identity Services


class RecruiterInfo(BaseModel):
    """Public recruiter information."""
    id: int
    email: str | None
    username: str | None = None
    name: str
    picture: str | None = None

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    """Successful authentication response."""
    token: str
    recruiter: RecruiterInfo


class PasswordCredentials(BaseModel):
    username: str = Field(min_length=3, max_length=40, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")
    password: SecretStr = Field(min_length=1, max_length=128)

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class RegistrationRequest(PasswordCredentials):
    email: str = Field(min_length=6, max_length=254)

    @field_validator("email")
    @classmethod
    def gmail_address(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r"[a-z0-9]+(?:\.[a-z0-9]+)*(?:\+[a-z0-9._-]+)?@(?:gmail\.com|googlemail\.com)", value):
            raise ValueError("Enter a valid Gmail address")
        return value.removesuffix("@googlemail.com") + "@gmail.com" if value.endswith("@googlemail.com") else value


class VerificationRequest(BaseModel):
    challenge_id: UUID
    code: SecretStr = Field(min_length=6, max_length=6)

    @field_validator("code")
    @classmethod
    def digits_only(cls, value):
        if not re.fullmatch(r"[0-9]{6}", value.get_secret_value()):
            raise ValueError("Enter the six-digit code")
        return value


class ResendRequest(BaseModel):
    challenge_id: UUID


class VerificationChallenge(BaseModel):
    challenge_id: UUID
    expires_in: int = 600
    resend_after: int = 60


def code_digest(challenge_id, email, code):
    message = f"signup-email:{challenge_id}:{email}:{code}".encode()
    return hmac.new(settings.jwt_secret.encode(), message, hashlib.sha256).hexdigest()


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


async def deliver_challenge(db, challenge, code):
    try:
        await asyncio.to_thread(verification_email.send_verification, challenge.email, code)
    except verification_email.EmailDeliveryError as exc:
        raise HTTPException(503, str(exc)) from None
    await db.execute(update(EmailVerification).where(
        EmailVerification.id == challenge.id, EmailVerification.code_digest == challenge.code_digest,
    ).values(delivered=1))
    await db.commit()
    return VerificationChallenge(challenge_id=challenge.id)


def auth_response(recruiter: Recruiter) -> AuthResponse:
    return AuthResponse(token=create_session_token(recruiter.id, recruiter.email),
                        recruiter=RecruiterInfo.model_validate(recruiter))


def check_password_attempt(request: Request, username: str, registering: bool):
    # Trust the server's resolved peer address, never a client-supplied header.
    peer = request.client.host if request.client else "unknown"
    passwords.throttle.check("registration" if registering else "login", peer, 10 if registering else 30, 300)
    if not registering:
        passwords.throttle.check("username", username, 10, 300)


@router.post("/register", response_model=VerificationChallenge, status_code=202)
async def register_with_password(body: RegistrationRequest, request: Request, db: AsyncSession = Depends(get_db)):
    check_password_attempt(request, body.username, True)
    password = body.password.get_secret_value()
    if not passwords.valid_new_password(password):
        raise HTTPException(422, "Use 8–128 characters and at least one special character, such as !, @, # or _.")
    passwords.throttle.check("verification-email", body.email, 5, 3600)
    if not verification_email.configured():
        raise HTTPException(503, "Email verification is not configured. Contact the administrator.")
    existing = await db.scalar(select(Recruiter.id).where(or_(
        Recruiter.username == body.username, func.lower(Recruiter.email) == body.email,
    )).limit(1))
    if existing is not None:
        raise HTTPException(409, "That username or email is already linked to an account. Sign in or use different details.")
    password_hash = await asyncio.to_thread(passwords.hash_password, password)
    now = datetime.now(timezone.utc)
    challenge_id, code = str(uuid4()), f"{secrets.randbelow(1_000_000):06d}"
    # Remove only expired temporary challenges, never existing accounts/results.
    await db.execute(delete(EmailVerification).where(EmailVerification.expires_at < now - timedelta(days=1)).execution_options(synchronize_session=False))
    challenge = EmailVerification(id=challenge_id, username=body.username, email=body.email,
        password_hash=password_hash, code_digest=code_digest(challenge_id, body.email, code),
        expires_at=now + timedelta(minutes=10), last_sent_at=now, attempts=0, send_count=1, delivered=0)
    db.add(challenge)
    await db.commit()
    return await deliver_challenge(db, challenge, code)


@router.post("/register/resend", response_model=VerificationChallenge)
async def resend_verification(body: ResendRequest, request: Request, db: AsyncSession = Depends(get_db)):
    peer = request.client.host if request.client else "unknown"
    passwords.throttle.check("resend-peer", peer, 10, 300)
    if not verification_email.configured():
        raise HTTPException(503, "Email verification is not configured. Contact the administrator.")
    challenge = await db.get(EmailVerification, str(body.challenge_id))
    now = datetime.now(timezone.utc)
    if challenge is None or utc(challenge.expires_at) <= now:
        raise HTTPException(400, "This signup has expired. Start again to get a new code.")
    if challenge.attempts >= 5 or challenge.send_count >= 4:
        raise HTTPException(429, "Verification limit reached. Start signup again later.")
    if utc(challenge.last_sent_at) > now - timedelta(seconds=60):
        raise HTTPException(429, "Wait 60 seconds between verification emails.", headers={"Retry-After":"60"})
    passwords.throttle.check("verification-email", challenge.email, 5, 3600)
    code = f"{secrets.randbelow(1_000_000):06d}"
    digest = code_digest(challenge.id, challenge.email, code)
    claimed = await db.scalar(update(EmailVerification).where(
        EmailVerification.id == challenge.id, EmailVerification.last_sent_at <= now - timedelta(seconds=60),
        EmailVerification.send_count < 4, EmailVerification.attempts < 5,
    ).values(code_digest=digest, expires_at=now+timedelta(minutes=10), last_sent_at=now,
             send_count=EmailVerification.send_count+1, delivered=0).returning(EmailVerification.id).execution_options(synchronize_session=False))
    if claimed is None:
        await db.rollback()
        raise HTTPException(429, "A new code was already requested. Please wait before trying again.")
    await db.commit()
    await db.refresh(challenge)
    return await deliver_challenge(db, challenge, code)


@router.post("/register/verify", response_model=AuthResponse, status_code=201)
async def verify_registration(body: VerificationRequest, request: Request, db: AsyncSession = Depends(get_db)):
    peer = request.client.host if request.client else "unknown"
    passwords.throttle.check("verify-peer", peer, 30, 300)
    challenge = await db.get(EmailVerification, str(body.challenge_id))
    now = datetime.now(timezone.utc)
    if challenge is None or utc(challenge.expires_at) <= now or not challenge.delivered:
        raise HTTPException(400, "This code is invalid or expired. Request a new code or start signup again.")
    if challenge.attempts >= 5:
        raise HTTPException(429, "Too many incorrect codes. Start signup again later.")
    if not hmac.compare_digest(challenge.code_digest, code_digest(challenge.id, challenge.email, body.code.get_secret_value())):
        await db.execute(update(EmailVerification).where(EmailVerification.id == challenge.id).values(attempts=EmailVerification.attempts+1))
        await db.commit()
        raise HTTPException(400, "Incorrect verification code. Please try again.")
    # Compare-and-delete makes a code single use, including concurrent requests.
    consumed = await db.scalar(delete(EmailVerification).where(
        EmailVerification.id == challenge.id, EmailVerification.code_digest == challenge.code_digest,
        EmailVerification.delivered == 1, EmailVerification.attempts < 5, EmailVerification.expires_at > now,
    ).returning(EmailVerification.id).execution_options(synchronize_session=False))
    if consumed is None:
        await db.rollback()
        raise HTTPException(400, "This code has already been used or replaced. Please sign in or request another code.")
    recruiter = Recruiter(username=challenge.username, email=challenge.email, password_hash=challenge.password_hash,
                          email_verified_at=now, name=challenge.username, approved=settings.allow_public_signup)
    db.add(recruiter)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "That username or email is already linked to an account. Sign in or use different details.")
    await db.refresh(recruiter)
    if not recruiter.approved:
        raise HTTPException(403, "Account created and pending approval — contact the administrator")
    return auth_response(recruiter)


@router.post("/password", response_model=AuthResponse)
async def sign_in_with_password(body: PasswordCredentials, request: Request, db: AsyncSession = Depends(get_db)):
    check_password_attempt(request, body.username, False)
    recruiter = await db.scalar(select(Recruiter).where(Recruiter.username == body.username))
    valid, upgraded_hash = await asyncio.to_thread(passwords.verify_password,
        recruiter.password_hash if recruiter else None, body.password.get_secret_value())
    if not valid or recruiter is None:
        raise HTTPException(401, "Incorrect username or password.")
    if settings.allow_public_signup and not recruiter.approved:
        recruiter.approved = True
    if not recruiter.approved:
        raise HTTPException(403, "Account pending approval — contact the administrator")
    if upgraded_hash:
        recruiter.password_hash = upgraded_hash
    recruiter.last_login = datetime.now(timezone.utc)
    await db.commit()
    return auth_response(recruiter)


@router.post("/google", response_model=AuthResponse)
async def sign_in_with_google(
    body: GoogleSignInRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Validate a Google ID token and return a session JWT.

    - Creates the recruiter account on first sign-in.
    - Open sign-up approves verified accounts, including previously pending ones.
    - Approval-only mode returns 403 for accounts that are not approved.
    """
    # 1. Verify the Google token
    try:
        id_info = await asyncio.to_thread(verify_google_token, body.credential)
    except AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

    google_id = id_info["sub"]
    email = id_info.get("email", "").strip().lower()
    name = id_info.get("name") or email
    picture = id_info.get("picture")

    # 2. Find or create the recruiter
    result = await db.execute(
        select(Recruiter).where(Recruiter.google_id == google_id)
    )
    recruiter = result.scalar_one_or_none()

    if recruiter is None:
        # Token verification above is required in both registration modes.
        allowed_emails = {value.strip().casefold() for value in settings.approved_recruiter_emails}
        recruiter = Recruiter(
            google_id=google_id,
            email=email,
            name=name,
            picture=picture,
            email_verified_at=datetime.now(timezone.utc),
            approved=settings.allow_public_signup or email.strip().casefold() in allowed_emails,
        )
        db.add(recruiter)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise HTTPException(409, "This email is linked to a username account. Sign in with that username and password.") from None
        await db.refresh(recruiter)

    # An account may have registered while approval-only mode was enabled.
    # Approve it only after a fresh, successful Google identity verification.
    if settings.allow_public_signup and not recruiter.approved:
        recruiter.approved = True

    # 3. Check approval
    if not recruiter.approved:
        raise HTTPException(
            status_code=403,
            detail="Account pending approval — contact the administrator",
        )

    # 4. Update last login and profile info
    recruiter.name = name
    recruiter.picture = picture
    recruiter.email_verified_at = datetime.now(timezone.utc)
    await db.commit()

    # 5. Issue session token
    token = create_session_token(recruiter.id, recruiter.email)

    return AuthResponse(
        token=token,
        recruiter=RecruiterInfo.model_validate(recruiter),
    )


@router.get("/me", response_model=RecruiterInfo)
async def get_me(recruiter: Recruiter = Depends(get_current_recruiter)):
    """Return the currently authenticated recruiter's profile."""
    return RecruiterInfo.model_validate(recruiter)
