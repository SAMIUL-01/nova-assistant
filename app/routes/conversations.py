"""
Conversation management endpoints.

GET    /api/conversations        -> sidebar list
POST   /api/conversations        -> create an empty chat
GET    /api/conversations/{id}   -> one chat with all messages
DELETE /api/conversations/{id}   -> remove chat + its messages
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from app.database import db
from app.services.auth import require_login
from app.models.schemas import (
    ConversationCreate,
    ConversationDetail,
    ConversationSummary,
    SimpleResult,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/conversations", tags=["conversations"],
                   dependencies=[Depends(require_login)])


@router.get("", response_model=List[ConversationSummary])
def list_conversations():
    """Newest-first list used to render the sidebar."""
    return db.list_conversations()


@router.post("", response_model=ConversationSummary, status_code=201)
def create_conversation(payload: ConversationCreate = ConversationCreate()):
    conversation = db.create_conversation(payload.title or "New Chat")
    conversation["message_count"] = 0
    return conversation


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(conversation_id: int):
    conversation = db.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return conversation


@router.delete("/{conversation_id}", response_model=SimpleResult)
def delete_conversation(conversation_id: int):
    deleted = db.delete_conversation(conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return SimpleResult(ok=True, detail="Conversation deleted.")
