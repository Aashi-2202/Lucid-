"""FastAPI dependencies for authentication."""

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthError, decode_session_token
from app.core.database import get_db
from app.models.recruiter import Recruiter

bearer_scheme = HTTPBearer()


async def get_current_recruiter(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Recruiter:
    """
    FastAPI dependency: extracts and validates the session JWT,
    loads the recruiter from the database, and checks approval status.
    """
    try:
        payload = decode_session_token(credentials.credentials)
    except AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

    recruiter_id = int(payload["sub"])
    result = await db.execute(
        select(Recruiter).where(Recruiter.id == recruiter_id)
    )
    recruiter = result.scalar_one_or_none()

    if recruiter is None:
        raise HTTPException(status_code=401, detail="Account not found")

    if not recruiter.approved:
        raise HTTPException(
            status_code=403,
            detail="Account pending approval — contact the administrator",
        )

    return recruiter
