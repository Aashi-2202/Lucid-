"""JWT and Google token utilities."""

from datetime import datetime, timedelta, timezone

import jwt
from google.auth.exceptions import GoogleAuthError
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
    if not settings.google_client_id or settings.google_client_id.startswith("your-client-id"):
        raise AuthError("Google sign-in is not configured. Contact the administrator.", 503)
    try:
        request = google_requests.Request()
        id_info = google_id_token.verify_oauth2_token(
            token, request, settings.google_client_id
        )
        # Ensure the token was issued by Google
        if id_info.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
            raise AuthError("Invalid token issuer")
        if id_info.get("email_verified") is not True or not id_info.get("email"):
            raise AuthError("Use a Google account with a verified email address.")
        if not isinstance(id_info.get("sub"), str) or not id_info["sub"]:
            raise AuthError("Google sign-in could not be verified. Please try again.")

        return id_info
    except ValueError as exc:
        raise AuthError("Google sign-in could not be verified. Please try again.") from exc
    except GoogleAuthError as exc:
        raise AuthError("Google sign-in is temporarily unavailable. Please try again.", 503) from exc


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
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp", "iat"]},
        )
        if not isinstance(payload["sub"], str) or not payload["sub"].isdigit() or int(payload["sub"]) < 1:
            raise AuthError("Invalid session. Please sign in again.")
        return payload
    except jwt.ExpiredSignatureError:
        raise AuthError("Session expired — please sign in again")
    except jwt.InvalidTokenError as exc:
        raise AuthError("Invalid session. Please sign in again.") from exc
