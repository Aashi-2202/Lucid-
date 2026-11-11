"""JWT and Google token utilities."""

from datetime import datetime, timedelta, timezone

import jwt
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from app.core.config import settings


class AuthError(Exception):
    """Raised when authentication fails."""

    def __init__(self, message: str, status_code: int = 401):
        self.message = message
        self.status_code = status_code


def verify_google_token(token: str) -> dict:
    """
    Verify a Google ID token and return the decoded payload.

    Returns dict with keys: sub, email, name, picture, etc.
    Raises AuthError on failure.
    """
    try:
        request = google_requests.Request()
        id_info = google_id_token.verify_oauth2_token(
            token, request, settings.google_client_id
        )
        # Ensure the token was issued by Google
        if id_info.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
            raise AuthError("Invalid token issuer")

        return id_info
    except ValueError as e:
        raise AuthError(f"Invalid Google token: {e}")


def create_session_token(recruiter_id: int, email: str) -> str:
    """Create a signed JWT session token for the recruiter."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(recruiter_id),
        "email": email,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expiry_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_session_token(token: str) -> dict:
    """
    Decode and verify a session JWT.

    Returns the payload dict. Raises AuthError on failure.
    """
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise AuthError("Session expired — please sign in again")
    except jwt.InvalidTokenError as e:
        raise AuthError(f"Invalid session token: {e}")
