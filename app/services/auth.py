"""
Optional password protection.

Nova on your own PC needs no login, so AUTH_PASSWORD is empty by default.
The moment Nova is reachable from the internet (Cloudflare Tunnel, Fly.io,
port forwarding) you MUST set a password -- otherwise anyone with the link
can use your API key, read your memories, and run actions on your computer.

Sessions are a signed cookie. No database table, no user accounts: one
password, one household.
"""

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time

from fastapi import HTTPException, Request

from app.config import BASE_DIR, settings

logger = logging.getLogger(__name__)

COOKIE_NAME = "nova_session"
_SECRET_FILE = BASE_DIR / "data" / ".session_secret"


def _secret() -> bytes:
    """A stable random secret, generated once and kept next to the database."""
    env_secret = (settings.__dict__.get("SESSION_SECRET") or "").strip() if hasattr(settings, "SESSION_SECRET") else ""
    if env_secret:
        return env_secret.encode()
    try:
        _SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
        if _SECRET_FILE.exists():
            value = _SECRET_FILE.read_text(encoding="utf-8").strip()
            if value:
                return value.encode()
        value = secrets.token_urlsafe(48)
        _SECRET_FILE.write_text(value, encoding="utf-8")
        return value.encode()
    except Exception:  # noqa: BLE001  (read-only filesystem, etc.)
        logger.warning("Could not persist the session secret; using a temporary one.")
        return secrets.token_urlsafe(48).encode()


def auth_required() -> bool:
    return bool(settings.AUTH_PASSWORD)


def _sign(payload: bytes) -> str:
    return hmac.new(_secret(), payload, hashlib.sha256).hexdigest()


def make_token() -> str:
    payload = json.dumps({
        "issued": int(time.time()),
        "expires": int(time.time()) + settings.SESSION_HOURS * 3600,
    }).encode()
    body = base64.urlsafe_b64encode(payload).decode()
    return f"{body}.{_sign(payload)}"


def token_is_valid(token: str) -> bool:
    if not token or "." not in token:
        return False
    body, signature = token.rsplit(".", 1)
    try:
        payload = base64.urlsafe_b64decode(body.encode())
    except Exception:  # noqa: BLE001
        return False
    if not hmac.compare_digest(_sign(payload), signature):
        return False
    try:
        data = json.loads(payload)
    except ValueError:
        return False
    return int(data.get("expires", 0)) > time.time()


def password_matches(candidate: str) -> bool:
    """Constant-time comparison, so timing cannot leak the password."""
    return hmac.compare_digest(
        (candidate or "").encode(), settings.AUTH_PASSWORD.encode()
    )


def is_logged_in(request: Request) -> bool:
    if not auth_required():
        return True
    return token_is_valid(request.cookies.get(COOKIE_NAME, ""))


def require_login(request: Request) -> None:
    """FastAPI dependency for protected API routes."""
    if not is_logged_in(request):
        raise HTTPException(status_code=401, detail="Please log in.")
