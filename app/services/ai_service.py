"""
AI service layer.

ALL provider/model logic lives here. Routes only call generate() or stream().
Swapping Nemotron for another OpenRouter model is a .env change, not a code change.
"""

import logging
import time
from typing import Dict, Iterator, List

from openai import OpenAI

from app.config import settings

logger = logging.getLogger(__name__)


class AIServiceError(Exception):
    """
    Raised when the AI provider cannot produce a response.

    The message is always safe to show to the user: it never contains the API
    key, a stack trace, or internal server details.
    """

    def __init__(self, user_message: str = "Sorry, something went wrong. Please try again."):
        super().__init__(user_message)
        self.user_message = user_message


class AIService:
    """Thin wrapper around an OpenAI-compatible chat completions endpoint."""

    def __init__(self, api_key: str = None, base_url: str = None, model: str = None):
        self.api_key = api_key if api_key is not None else settings.OPENROUTER_API_KEY
        self.base_url = base_url or settings.OPENROUTER_BASE_URL
        self.model = model or settings.AI_MODEL
        self._client = None

    # -- provider client ---------------------------------------------------
    @property
    def client(self) -> OpenAI:
        """Create the HTTP client lazily so the app can boot without a key."""
        if self._client is None:
            if not self.api_key:
                raise AIServiceError(
                    "No AI API key is configured on the server. "
                    "Add OPENROUTER_API_KEY to your .env file and restart."
                )
            self._client = OpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                timeout=settings.AI_TIMEOUT_SECONDS,
                max_retries=1,
                default_headers={
                    # Optional OpenRouter attribution headers.
                    "HTTP-Referer": settings.SITE_URL,
                    "X-Title": settings.APP_NAME,
                },
            )
        return self._client

    # -- message building --------------------------------------------------
    def build_messages(
        self, history: List[Dict[str, str]], extra_context: str = ""
    ) -> List[Dict[str, str]]:
        """
        Prepend the system prompt to the conversation history.

        extra_context carries long-term memories and document excerpts. It is
        appended to the system prompt so it applies to the whole exchange.
        """
        system = settings.SYSTEM_PROMPT
        if extra_context:
            system = f"{system}\n\n{extra_context}"

        messages = [{"role": "system", "content": system}]
        for item in history:
            role = item.get("role")
            content = (item.get("content") or "").strip()
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
        return messages

    # -- raw call (used by the memory extractor) ---------------------------
    def generate_raw(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = None,
        temperature: float = None,
    ) -> str:
        """
        Send messages exactly as given, with no system prompt or memory added.

        Used for internal jobs like fact extraction, where the app needs a
        plain, deterministic answer rather than a chat reply.
        """
        if settings.AI_OFFLINE_MOCK:
            return "[]"
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=settings.AI_TEMPERATURE if temperature is None else temperature,
                max_tokens=max_tokens or settings.AI_MAX_TOKENS,
            )
        except AIServiceError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("Internal AI request failed: %s", type(exc).__name__)
            raise AIServiceError(_friendly_error(exc)) from exc
        return _extract_content(response)

    # -- non-streaming -----------------------------------------------------
    def generate(self, history: List[Dict[str, str]], extra_context: str = "") -> str:
        """Return the complete AI reply as a single string."""
        if settings.AI_OFFLINE_MOCK:
            return _mock_reply(history, extra_context)

        messages = self.build_messages(history, extra_context)
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=settings.AI_TEMPERATURE,
                max_tokens=settings.AI_MAX_TOKENS,
            )
        except AIServiceError:
            raise
        except Exception as exc:  # noqa: BLE001 - provider errors vary widely
            logger.exception("AI request failed")
            raise AIServiceError(_friendly_error(exc)) from exc

        content = _extract_content(response)
        if not content:
            logger.error("AI returned an empty/malformed payload: %r", response)
            raise AIServiceError(
                "The AI returned an empty response. Please try sending your message again."
            )
        return content

    # -- streaming (Server-Sent Events source) -----------------------------
    def stream(
        self, history: List[Dict[str, str]], extra_context: str = ""
    ) -> Iterator[str]:
        """Yield the reply in small text chunks as they arrive."""
        if settings.AI_OFFLINE_MOCK:
            for chunk in _mock_reply(history, extra_context).split(" "):
                time.sleep(0.02)
                yield chunk + " "
            return

        messages = self.build_messages(history, extra_context)
        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=settings.AI_TEMPERATURE,
                max_tokens=settings.AI_MAX_TOKENS,
                stream=True,
            )
            for event in stream:
                if not getattr(event, "choices", None):
                    continue
                delta = getattr(event.choices[0], "delta", None)
                piece = getattr(delta, "content", None) if delta else None
                if piece:
                    yield piece
        except AIServiceError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("AI streaming request failed")
            raise AIServiceError(_friendly_error(exc)) from exc


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _extract_content(response) -> str:
    """Defensively pull the text out of a chat completion response."""
    try:
        return (response.choices[0].message.content or "").strip()
    except (AttributeError, IndexError, TypeError):
        return ""


def _friendly_error(exc: Exception) -> str:
    """Translate a provider exception into a message that is safe to display."""
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    name = type(exc).__name__.lower()

    if status == 401 or "authentication" in name:
        return "The AI API key was rejected. Please check OPENROUTER_API_KEY in your .env file."
    if status == 402:
        return "This model requires credits on your OpenRouter account."
    if status == 404:
        return (
            f"The model '{settings.AI_MODEL}' was not found. "
            "Check the AI_MODEL value in your .env file."
        )
    if status == 429 or "ratelimit" in name:
        return "The AI is rate limited right now. Please wait a moment and try again."
    if status and 500 <= int(status) < 600:
        return "The AI provider is having trouble right now. Please try again shortly."
    if "timeout" in name or "timeout" in str(exc).lower():
        return "The AI took too long to respond. Please try again."
    if "connection" in name or "apiconnection" in name:
        return "Could not reach the AI provider. Please check your internet connection."
    return "Sorry, something went wrong. Please try again."


def _mock_reply(history: List[Dict[str, str]], extra_context: str = "") -> str:
    """Offline stand-in used when AI_OFFLINE_MOCK=1, for testing without a key."""
    last_user = ""
    for item in reversed(history):
        if item.get("role") == "user":
            last_user = (item.get("content") or "").strip()
            break
    turns = len([h for h in history if h.get("role") == "user"])

    context_note = ""
    if extra_context:
        has_memory = "What you know about the user" in extra_context
        has_docs = "Attached document excerpts" in extra_context
        bits = []
        if has_memory:
            bits.append("long-term memory")
        if has_docs:
            bits.append("document excerpts")
        context_note = (
            f"\n\nContext received: {' + '.join(bits)} "
            f"({len(extra_context)} characters).\n"
        )

    return (
        "**Offline mock mode is on.** No request was sent to OpenRouter.\n\n"
        f"You said: *{last_user or '(nothing)'}*\n\n"
        f"This conversation has {turns} user message(s), which proves memory is working."
        f"{context_note}\n"
        "```python\n"
        'print("Streaming, markdown, and code blocks all render correctly.")\n'
        "```\n\n"
        "Set `AI_OFFLINE_MOCK=0` in your `.env` to talk to the real model."
    )


# A single shared instance used by the routes.
ai_service = AIService()
