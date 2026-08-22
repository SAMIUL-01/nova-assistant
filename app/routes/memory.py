"""
Long-term memory endpoints.

GET    /api/memory        -> everything the assistant knows about you
POST   /api/memory        -> add a fact yourself
DELETE /api/memory/{id}   -> forget one fact
DELETE /api/memory        -> forget everything
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.config import settings
from app.database import db
from app.models.schemas import MemoryCreate, MemoryOut, SimpleResult
from app.services.auth import require_login

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/memory", tags=["memory"],
                   dependencies=[Depends(require_login)])


@router.get("")
def list_memory():
    """Full transparency: every stored fact, so nothing is remembered secretly."""
    facts = db.list_memories()
    return {
        "enabled": settings.MEMORY_ENABLED,
        "count": len(facts),
        "max": settings.MEMORY_MAX_FACTS,
        "facts": facts,
    }


@router.post("", response_model=MemoryOut, status_code=201)
def create_memory(payload: MemoryCreate):
    row = db.add_memory(payload.content, source="manual", pinned=1)
    if row is None:
        raise HTTPException(status_code=409, detail="That fact is already remembered.")
    return row


@router.delete("/{memory_id}", response_model=SimpleResult)
def forget_memory(memory_id: int):
    if not db.delete_memory(memory_id):
        raise HTTPException(status_code=404, detail="That memory does not exist.")
    return SimpleResult(ok=True, detail="Forgotten.")


@router.delete("", response_model=SimpleResult)
def forget_all():
    removed = db.clear_memories()
    logger.info("Cleared %s memories at the user's request", removed)
    return SimpleResult(ok=True, detail=f"Forgot {removed} fact(s).")
