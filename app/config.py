"""
Central configuration.

Every tunable value lives here and is read from the .env file, so changing the
AI model or the app name never requires touching application code.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# BASE_DIR = the nova/ folder (one level above app/)
BASE_DIR = Path(__file__).resolve().parent.parent

# Load the .env file that sits next to this project.
load_dotenv(BASE_DIR / ".env")


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_api_key(name: str) -> str:
    """Read an API key, treating the .env.example placeholder as 'not set'."""
    value = (os.getenv(name) or "").strip().strip('"').strip("'")
    if value.upper().startswith("YOUR_API_KEY"):
        return ""
    return value


DEFAULT_SYSTEM_PROMPT = (
    "You are Nova, a cute anime-style female AI assistant.\n"
    "If someone asks who you are, say you are Nova. Do not name the underlying "
    "model unless you are asked directly about it.\n"
    "\n"
    "Personality: intelligent, calm, friendly, caring, confident and slightly "
    "playful. Warm and natural, never robotic and never childish.\n"
    "\n"
    "How you talk:\n"
    "- Keep replies short and easy to say out loud; they are often spoken.\n"
    "- Be encouraging, but never fake or over-excited.\n"
    "- A light touch of playfulness is good. Do not overuse emoji.\n"
    "- If the user writes in Bangla or Banglish, reply the same way.\n"
    "\n"
    "How you work:\n"
    "- Give accurate, clear, useful answers, and explain step by step when "
    "the question is technical.\n"
    "- If the user asks for code, provide clean, working code.\n"
    "- Never claim to have done something you did not actually do.\n"
    "- When an action needs the user's confirmation, say so plainly and wait."
)


class Settings:
    """All application settings in one object."""

    # --- App ---
    APP_NAME: str = os.getenv("APP_NAME", "Nova")
    DEBUG: bool = _env_bool("DEBUG", False)

    # --- AI provider (OpenRouter is OpenAI-API compatible) ---
    OPENROUTER_API_KEY: str = _env_api_key("OPENROUTER_API_KEY")
    OPENROUTER_BASE_URL: str = os.getenv(
        "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
    )
    AI_MODEL: str = os.getenv("AI_MODEL", "nvidia/nemotron-3.5-lightning:free")
    AI_TEMPERATURE: float = _env_float("AI_TEMPERATURE", 0.7)
    AI_MAX_TOKENS: int = _env_int("AI_MAX_TOKENS", 2048)
    AI_TIMEOUT_SECONDS: float = _env_float("AI_TIMEOUT_SECONDS", 90.0)

    # Optional OpenRouter attribution headers (safe to leave blank).
    SITE_URL: str = os.getenv("SITE_URL", "http://localhost:8000")

    # Set AI_OFFLINE_MOCK=1 to run the whole app with a fake AI.
    # Useful for testing the UI without an API key or internet connection.
    AI_OFFLINE_MOCK: bool = _env_bool("AI_OFFLINE_MOCK", False)

    # --- Behaviour ---
    SYSTEM_PROMPT: str = os.getenv("SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT)
    MAX_MESSAGE_CHARS: int = _env_int("MAX_MESSAGE_CHARS", 10_000)
    # How many past messages (user+assistant) get sent back as memory.
    HISTORY_LIMIT: int = _env_int("HISTORY_LIMIT", 20)

    # --- Storage ---
    DB_PATH: Path = Path(os.getenv("DB_PATH", BASE_DIR / "data" / "chat.db"))
    UPLOAD_DIR: Path = Path(os.getenv("UPLOAD_DIR", BASE_DIR / "data" / "uploads"))

    # --- Long-term memory (facts remembered across every chat) ---
    MEMORY_ENABLED: bool = _env_bool("MEMORY_ENABLED", True)
    # Ask the AI to spot facts too (costs one extra small request per reply).
    MEMORY_AI_EXTRACTION: bool = _env_bool("MEMORY_AI_EXTRACTION", True)
    MEMORY_MAX_FACTS: int = _env_int("MEMORY_MAX_FACTS", 120)

    # --- File uploads / document Q&A ---
    MAX_UPLOAD_MB: int = _env_int("MAX_UPLOAD_MB", 10)
    DOC_CHUNK_CHARS: int = _env_int("DOC_CHUNK_CHARS", 1400)
    DOC_CHUNK_OVERLAP: int = _env_int("DOC_CHUNK_OVERLAP", 180)
    # Total characters of document excerpts sent with a question.
    DOC_CONTEXT_CHARS: int = _env_int("DOC_CONTEXT_CHARS", 6000)
    DOC_MAX_CHUNKS: int = _env_int("DOC_MAX_CHUNKS", 6)

    # --- Security ---
    # Requests per minute per IP for /api/chat and /api/upload. 0 = disabled.
    RATE_LIMIT_PER_MINUTE: int = _env_int("RATE_LIMIT_PER_MINUTE", 60)

    # Password for the login page. Empty = no login (fine on your own PC,
    # NEVER leave empty if Nova is reachable from the internet).
    AUTH_PASSWORD: str = (os.getenv("AUTH_PASSWORD") or "").strip()
    SESSION_HOURS: int = _env_int("SESSION_HOURS", 720)   # 30 days

    # --- Actions ("JARVIS mode") ---
    # Let Nova actually DO things on this computer: open sites and apps,
    # manage files, run git. Only ever works on the machine Nova runs on.
    ACTIONS_ENABLED: bool = _env_bool("ACTIONS_ENABLED", True)
    # Ask before anything destructive (deleting/moving files, git push).
    ACTIONS_CONFIRM: bool = _env_bool("ACTIONS_CONFIRM", True)
    # Paranoid mode: also ask before harmless-but-visible things such as
    # creating a file or opening an app.
    STRICT_CONFIRM: bool = _env_bool("STRICT_CONFIRM", False)
    # Nova may only touch files inside this folder. Nothing outside it.
    NOVA_WORKSPACE: Path = Path(
        os.getenv("NOVA_WORKSPACE", "") or (Path.home() / "Nova")
    )
    # Folder that git commands may run in (defaults to the workspace).
    GIT_ROOT: Path = Path(os.getenv("GIT_ROOT", "") or (Path.home() / "Nova"))
    ACTION_LOG: Path = Path(
        os.getenv("ACTION_LOG", "") or (BASE_DIR / "data" / "actions.log")
    )
    MAX_TOOL_ROUNDS: int = _env_int("MAX_TOOL_ROUNDS", 4)

    # Comma-separated list, or "*" for any origin (fine for local development).
    ALLOWED_ORIGINS: list = [
        o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()
    ]

    @property
    def has_api_key(self) -> bool:
        return bool(self.OPENROUTER_API_KEY)


settings = Settings()
