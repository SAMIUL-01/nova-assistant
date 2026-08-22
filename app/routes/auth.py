"""Login and logout (only active when AUTH_PASSWORD is set)."""

import logging

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from app.config import settings
from app.models.schemas import LoginRequest, SimpleResult
from app.services import auth
from app.services.rate_limit import client_key, limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/login", response_model=SimpleResult)
def login(payload: LoginRequest, request: Request, response: Response):
    """Exchange the password for a signed session cookie."""
    if not auth.auth_required():
        return SimpleResult(ok=True, detail="No password is set on this Nova.")

    # Reuse the rate limiter so the password cannot be brute forced.
    allowed, retry_after, _ = limiter.check(f"login:{client_key(request)}")
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={"detail": f"Too many attempts. Wait {retry_after} seconds."},
        )

    if not auth.password_matches(payload.password):
        logger.warning("Failed login from %s", client_key(request))
        return JSONResponse(status_code=401, content={"detail": "Wrong password."})

    response.set_cookie(
        auth.COOKIE_NAME,
        auth.make_token(),
        max_age=settings.SESSION_HOURS * 3600,
        httponly=True,
        samesite="lax",
        secure=False,   # works on http://localhost; browsers still send it over https
        path="/",
    )
    logger.info("Login succeeded from %s", client_key(request))
    return SimpleResult(ok=True, detail="Welcome back.")


@router.post("/logout", response_model=SimpleResult)
def logout(response: Response):
    response.delete_cookie(auth.COOKIE_NAME, path="/")
    return SimpleResult(ok=True, detail="Logged out.")


@router.get("/auth/status")
def auth_status(request: Request):
    return {
        "password_set": auth.auth_required(),
        "logged_in": auth.is_logged_in(request),
    }
