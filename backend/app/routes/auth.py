"""Authentication routes — Google Sign-In and session management."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthError, create_session_token, verify_google_token
from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_recruiter
from app.models.recruiter import Recruiter

router = APIRouter(prefix="/auth", tags=["auth"])


class GoogleSignInRequest(BaseModel):
    """Request body for Google Sign-In."""
    credential: str  # The ID token from Google Identity Services


class RecruiterInfo(BaseModel):
    """Public recruiter information."""
    id: int
    email: str
    name: str
    picture: str | None = None

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    """Successful authentication response."""
    token: str
    recruiter: RecruiterInfo


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
