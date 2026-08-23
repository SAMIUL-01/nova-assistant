"""
FastAPI application entry point.

Run with:  uvicorn app.main:app --reload
"""

import logging
import mimetypes
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.cors import CORSMiddleware

from app.config import BASE_DIR, settings
from app.database.db import DatabaseError, init_db
from app.routes import actions as actions_routes
from app.routes import auth as auth_routes
from app.routes import chat, conversations, memory
from app.routes import permissions as permissions_routes
from app.services import auth as auth_service

# File uploads need the optional 'python-multipart' package. If it is missing,
# the rest of the app must still work -- so import the upload routes defensively
# instead of letting the whole server refuse to start.
try:
    from app.routes import uploads
    UPLOADS_AVAILABLE = True
    UPLOADS_ERROR = ""
except (ImportError, RuntimeError, AssertionError) as _exc:  # pragma: no cover
    uploads = None
    UPLOADS_AVAILABLE = False
    UPLOADS_ERROR = str(_exc)

# --------------------------------------------------------------------------
# Logging: technical detail goes to the console, never to the browser.
# --------------------------------------------------------------------------
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("app")


# --------------------------------------------------------------------------
# Startup / shutdown
# --------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Runs once on startup: make sure the database file and tables exist."""
    init_db()
    logger.info("%s starting up", settings.APP_NAME)
    logger.info("Model: %s", settings.AI_MODEL)
    if settings.AI_OFFLINE_MOCK:
        logger.warning("AI_OFFLINE_MOCK=1 -> using fake replies, no API calls.")
    elif not settings.has_api_key:
        logger.warning(
            "No OPENROUTER_API_KEY found. Add it to .env or set AI_OFFLINE_MOCK=1."
        )
    if settings.ACTIONS_ENABLED:
        logger.info("Actions ENABLED. Workspace: %s", settings.NOVA_WORKSPACE)
        if not auth_service.auth_required():
            logger.warning(
                "No AUTH_PASSWORD set. That is fine on your own PC, but set one "
                "before exposing Nova to the internet -- actions run on THIS machine."
            )
    else:
        logger.info("Actions disabled (ACTIONS_ENABLED=false).")
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title=settings.APP_NAME,
    description="Personal AI chat web app powered by OpenRouter.",
    version="1.0.0",
    lifespan=lifespan,
)

# --------------------------------------------------------------------------
# CORS
# --------------------------------------------------------------------------
# A wildcard origin and credentials cannot legally be combined, and browsers
# reject that pair. The frontend is served from the same origin anyway.
_allow_all_origins = "*" in settings.ALLOWED_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=not _allow_all_origins,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# --------------------------------------------------------------------------
# Static files and templates
# --------------------------------------------------------------------------
# Windows does not know this type by default, and the browser needs it to
# accept the web app manifest (which is what makes Nova installable).
mimetypes.add_type("application/manifest+json", ".webmanifest")

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# --------------------------------------------------------------------------
# Routers
# --------------------------------------------------------------------------
app.include_router(auth_routes.router)
app.include_router(conversations.router)
app.include_router(chat.router)
app.include_router(memory.router)
app.include_router(actions_routes.router)
app.include_router(permissions_routes.router)

if UPLOADS_AVAILABLE:
    app.include_router(uploads.router)
else:
    # Graceful degradation: chat still works, the attach button just hides.
    from fastapi import HTTPException

    _FIX = ("File upload is turned off because the 'python-multipart' package "
            "is missing. Activate your venv and run: "
            "pip install -r requirements.txt")

    @app.get("/api/upload/info", tags=["documents"])
    def upload_info_unavailable():
        return {"enabled": False, "max_mb": 0, "extensions": [], "reason": _FIX}

    @app.post("/api/upload", tags=["documents"])
    def upload_unavailable():
        raise HTTPException(status_code=503, detail=_FIX)


# --------------------------------------------------------------------------
# Error handlers: friendly text out, full detail in the logs
# --------------------------------------------------------------------------
@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    message = str(first.get("msg", "Invalid request."))
    message = message.replace("Value error, ", "")
    logger.info("Validation error on %s: %s", request.url.path, exc.errors())
    return JSONResponse(status_code=400, content={"detail": message})


@app.exception_handler(DatabaseError)
async def database_error_handler(request: Request, exc: DatabaseError):
    logger.error("Database failure on %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "A storage error occurred. Please try again."},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Sorry, something went wrong. Please try again."},
    )


# --------------------------------------------------------------------------
# Pages / meta
# --------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
def home(request: Request):
    """Serve the chat UI, or the login page when a password is set."""
    if not auth_service.is_logged_in(request):
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "app_name": settings.APP_NAME,
            "max_chars": settings.MAX_MESSAGE_CHARS,
        },
    )


@app.get("/login", include_in_schema=False)
def login_page(request: Request):
    if not auth_service.auth_required() or auth_service.is_logged_in(request):
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(
        request=request, name="login.html", context={"app_name": settings.APP_NAME}
    )


@app.get("/api/health", tags=["meta"])
def health(request: Request):
    """Quick check that the server is up and how it is configured."""
    return {
        "status": "ok",
        "app_name": settings.APP_NAME,
        "model": settings.AI_MODEL,
        "api_key_configured": settings.has_api_key,
        "offline_mock": settings.AI_OFFLINE_MOCK,
        "memory_enabled": settings.MEMORY_ENABLED,
        "uploads_available": UPLOADS_AVAILABLE,
        "actions_enabled": settings.ACTIONS_ENABLED,
        "password_set": auth_service.auth_required(),
        "logged_in": auth_service.is_logged_in(request),
    }
