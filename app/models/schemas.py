"""
Pydantic request/response models.

These give automatic input validation and self-documenting API docs at /docs.
"""

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from app.config import settings


class ChatRequest(BaseModel):
    conversation_id: Optional[int] = Field(
        default=None,
        description="Existing conversation id. If omitted, a new chat is created.",
    )
    message: str = Field(..., description="The user's message.")

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("Message cannot be empty.")
        if len(cleaned) > settings.MAX_MESSAGE_CHARS:
            raise ValueError(
                f"Message is too long. Maximum is {settings.MAX_MESSAGE_CHARS} characters."
            )
        return cleaned


class ChatResponse(BaseModel):
    conversation_id: int
    message: str
    title: str
    actions: List[dict] = []
    pending: List[dict] = []


class ConversationCreate(BaseModel):
    title: Optional[str] = Field(default="New Chat", max_length=80)


class ConversationSummary(BaseModel):
    id: int
    title: str
    created_at: str
    updated_at: str
    message_count: int = 0


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    created_at: str


class ConversationDetail(BaseModel):
    id: int
    title: str
    created_at: str
    updated_at: str
    messages: List[MessageOut] = []


class SimpleResult(BaseModel):
    ok: bool
    detail: str = ""


class LoginRequest(BaseModel):
    password: str = Field(..., description="The password from AUTH_PASSWORD.")


class ActionToken(BaseModel):
    token: str = Field(..., min_length=8, description="Pending action token.")


class PermissionUpdate(BaseModel):
    enabled: bool = Field(..., description="Is this capability switched on?")
    always_ask: bool = Field(default=False,
                             description="Confirm every use, even safe ones.")


class MemoryCreate(BaseModel):
    content: str = Field(..., description="A fact to remember about the user.")

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if len(cleaned) < 3:
            raise ValueError("A memory needs at least 3 characters.")
        if len(cleaned) > 200:
            raise ValueError("A memory must be 200 characters or fewer.")
        return cleaned


class MemoryOut(BaseModel):
    id: int
    content: str
    source: str = "auto"
    pinned: int = 0
    source_conversation: Optional[int] = None
    created_at: str
