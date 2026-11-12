"""Authentication routes — Google Sign-In and session management."""

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, SecretStr, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthError, create_session_token, verify_google_token
from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_recruiter
from app.core import passwords
from app.models.recruiter import Recruiter

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


def auth_response(recruiter: Recruiter) -> AuthResponse:
    return AuthResponse(token=create_session_token(recruiter.id, recruiter.email),
                        recruiter=RecruiterInfo.model_validate(recruiter))


def check_password_attempt(request: Request, username: str, registering: bool):
    # Trust the server's resolved peer address, never a client-supplied header.
    peer = request.client.host if request.client else "unknown"
    passwords.throttle.check("registration" if registering else "login", peer, 10 if registering else 30, 300)
    if not registering:
        passwords.throttle.check("username", username, 10, 300)


@router.post("/register", response_model=AuthResponse, status_code=201)
async def register_with_password(body: PasswordCredentials, request: Request, db: AsyncSession = Depends(get_db)):
    check_password_attempt(request, body.username, True)
    password = body.password.get_secret_value()
    if len(password) < 12 or not password.strip():
        raise HTTPException(422, "Use a password with at least 12 characters, not only spaces.")
    # Hash even on a duplicate to avoid a cheap account-existence timing shortcut.
    password_hash = await asyncio.to_thread(passwords.hash_password, password)
    recruiter = Recruiter(username=body.username, password_hash=password_hash,
                          name=body.username, approved=settings.allow_public_signup)
    db.add(recruiter)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "That username is already taken. Choose another username or sign in.")
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
    email = id_info.get("email", "")
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
            approved=settings.allow_public_signup or email.strip().casefold() in allowed_emails,
        )
        db.add(recruiter)
        await db.commit()
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
