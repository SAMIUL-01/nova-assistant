"""
File upload endpoints.

POST   /api/upload                      -> upload a file to a conversation
GET    /api/conversations/{id}/documents -> files attached to a conversation
DELETE /api/documents/{id}              -> remove a file
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.config import settings
from app.database import db
from app.models.schemas import SimpleResult
from app.services.documents import DocumentError, SUPPORTED, remove_document, store_upload
from app.services.auth import require_login
from app.services.rate_limit import enforce_rate_limit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["documents"],
                   dependencies=[Depends(require_login)])


@router.get("/upload/info")
def upload_info():
    """What the frontend needs to know before showing the attach button."""
    return {
        "enabled": True,
        "max_mb": settings.MAX_UPLOAD_MB,
        "extensions": sorted(SUPPORTED.keys()),
    }


@router.post("/upload", status_code=201, dependencies=[Depends(enforce_rate_limit)])
async def upload_file(
    file: UploadFile = File(...),
    conversation_id: Optional[int] = Form(default=None),
):
    """Accept a document, extract its text, and attach it to a conversation."""
    if conversation_id is not None and not db.conversation_exists(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found.")

    try:
        raw = await file.read()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Upload read failed")
        raise HTTPException(status_code=400, detail="That file could not be read.") from exc
    finally:
        await file.close()

    try:
        record = store_upload(
            raw=raw,
            filename=file.filename or "upload",
            media_type=file.content_type or "",
            conversation_id=conversation_id,
        )
    except DocumentError as exc:
        # These messages are written for the user, so pass them straight through.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "id": record["id"],
        "filename": record["filename"],
        "size_bytes": record["size_bytes"],
        "text_chars": record["text_chars"],
        "chunk_count": record["chunk_count"],
        "conversation_id": record["conversation_id"],
    }


@router.get("/conversations/{conversation_id}/documents")
def conversation_documents(conversation_id: int):
    if not db.conversation_exists(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return db.list_documents(conversation_id)


@router.delete("/documents/{document_id}", response_model=SimpleResult)
def delete_document(document_id: int):
    if not remove_document(document_id):
        raise HTTPException(status_code=404, detail="That file does not exist.")
    return SimpleResult(ok=True, detail="File removed.")
