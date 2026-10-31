"""Single-user, signed HttpOnly session for private hackathon cases."""

import hashlib
import hmac
import os
import time

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

load_dotenv()

router = APIRouter(prefix="/auth", tags=["auth"])
COOKIE = "blackbox_session"
SESSION_SECONDS = 12 * 60 * 60


def _secret() -> bytes:
    value = os.getenv("SECRET_KEY", "")
    if len(value) < 32 or value == "change-me-in-prod":
        raise RuntimeError("Set SECRET_KEY to a random value of at least 32 characters")
    return value.encode()


def _password() -> str:
    value = os.getenv("BLACKBOX_ACCESS_PASSWORD", "")
    if not value:
        raise RuntimeError("Set BLACKBOX_ACCESS_PASSWORD before starting the API")
    return value


def _signature(expiry: int) -> str:
    return hmac.new(_secret(), f"blackbox:{expiry}".encode(), hashlib.sha256).hexdigest()


def is_authenticated(request: Request) -> bool:
    token = request.cookies.get(COOKIE, "")
    try:
        expiry_text, signature = token.split(".", 1)
        expiry = int(expiry_text)
    except (ValueError, TypeError):
        return False
    return expiry > time.time() and hmac.compare_digest(signature, _signature(expiry))


class LoginRequest(BaseModel):
    password: str


@router.post("/session")
def login(payload: LoginRequest, response: Response) -> dict[str, bool]:
    if not hmac.compare_digest(payload.password, _password()):
        raise HTTPException(status_code=401, detail="Incorrect access password")
    expiry = int(time.time()) + SESSION_SECONDS
    response.set_cookie(
        COOKIE,
        f"{expiry}.{_signature(expiry)}",
        httponly=True,
        secure=os.getenv("APP_ENV") == "production",
        samesite="lax",
        max_age=SESSION_SECONDS,
        path="/api/v1",
    )
    return {"authenticated": True}


@router.get("/session")
def session(request: Request) -> dict[str, bool]:
    return {"authenticated": is_authenticated(request)}


@router.delete("/session")
def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(COOKIE, path="/api/v1")
    return {"authenticated": False}


# ── FastAPI dependency ──────────────────────────────────────────────────────────


def current_user(request: Request) -> str:
    """
    FastAPI dependency that returns a user identifier string.

    Phase 1/2: single-user session — always returns "demo-user" when the
    cookie is valid (authentication is enforced by the global middleware).
    Phase 3+: replace with JWT sub claim or DB lookup.
    """
    return "demo-user"
