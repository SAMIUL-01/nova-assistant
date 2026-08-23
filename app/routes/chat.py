"""
Chat endpoints.

POST /api/chat         -> full response in one JSON payload
POST /api/chat/stream  -> Server-Sent Events, token by token

Context sent to the model = conversation history + long-term memories +
relevant document excerpts. When actions are enabled the model can also call
tools, and those steps are streamed to the browser as they happen.
"""

import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.config import settings
from app.database import db
from app.models.schemas import ChatRequest, ChatResponse
from app.services import agent, documents, memory
from app.services import router as command_router
from app.services.ai_service import AIServiceError, ai_service
from app.services.auth import require_login
from app.services.rate_limit import enforce_rate_limit
from app.services.titles import make_title

logger = logging.getLogger(__name__)

# Every route here costs an AI request, so all of them are rate limited.
router = APIRouter(
    prefix="/api",
    tags=["chat"],
    dependencies=[Depends(require_login), Depends(enforce_rate_limit)],
)


def _prepare_turn(payload: ChatRequest):
    """
    Shared setup for both chat endpoints:

    1. Find or create the conversation.
    2. Auto-title it if this is the first message.
    3. Save the user's message.
    4. Build the extra context (memories + document excerpts).
    """
    conversation_id = payload.conversation_id

    if conversation_id is None:
        conversation = db.create_conversation(make_title(payload.message))
        conversation_id = conversation["id"]
        title = conversation["title"]
    else:
        conversation = db.get_conversation(conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        title = conversation["title"]
        if not conversation["messages"] and title in ("New Chat", "", None):
            title = make_title(payload.message)
            db.rename_conversation(conversation_id, title)

    db.add_message(conversation_id, "user", payload.message)
    history = db.get_history(conversation_id)

    blocks = []
    memory_block = memory.format_for_prompt()
    if memory_block:
        blocks.append(memory_block)
    doc_block = documents.build_context(conversation_id, payload.message)
    if doc_block:
        blocks.append(doc_block)

    return conversation_id, title, history, "\n\n".join(blocks)


def _learn(conversation_id: int, user_message: str, reply: str) -> None:
    """Background job: pick up any durable facts from this exchange."""
    try:
        memory.learn_from_exchange(conversation_id, user_message, reply)
    except Exception:  # noqa: BLE001
        logger.exception("Background memory update failed")


def _use_agent() -> bool:
    """Tools only make sense with a real model and actions switched on."""
    return settings.ACTIONS_ENABLED and not settings.AI_OFFLINE_MOCK


def _fast_path(message: str):
    """
    Try the router first. Typed and spoken commands both arrive here, so the
    two can never behave differently.

    Needs no model, so it works even in offline mock mode.
    """
    if not settings.ACTIONS_ENABLED:
        return None
    return command_router.route(message)


def _transcript(text: str, tool_lines: list) -> str:
    """What gets saved to history, so past chats still show what Nova did."""
    saved = text.strip()
    if tool_lines:
        done = "\n".join(f"*✓ {line}*" for line in tool_lines)
        saved = f"{saved}\n\n{done}" if saved else done
    return saved


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, background: BackgroundTasks):
    """Send a message and get the complete reply back."""
    conversation_id, title, history, extra_context = _prepare_turn(payload)

    tools_used, pending = [], []

    routed = _fast_path(payload.message)
    if routed is not None:
        parts = []
        for event in agent.run_routed(routed, conversation_id):
            if event["type"] == "text":
                parts.append(event["text"])
            elif event["type"] == "tool":
                tools_used.append({"detail": event["detail"], "result": event["result"]})
            elif event["type"] == "confirm":
                pending.append({"token": event["token"], "detail": event["detail"]})
        reply = "".join(parts)
    elif _use_agent():
        parts = []
        failure = None
        for event in agent.run_agent(history, extra_context, conversation_id):
            kind = event["type"]
            if kind == "text":
                parts.append(event["text"])
            elif kind == "tool":
                tools_used.append({"detail": event["detail"], "result": event["result"]})
            elif kind == "confirm":
                pending.append({"token": event["token"], "detail": event["detail"]})
            elif kind == "error":
                failure = event["detail"]
        if failure and not parts:
            raise HTTPException(status_code=502, detail=failure)
        reply = "".join(parts)
    else:
        try:
            reply = ai_service.generate(history, extra_context=extra_context)
        except AIServiceError as exc:
            raise HTTPException(status_code=502, detail=exc.user_message) from exc

    saved = _transcript(reply, [t["detail"] for t in tools_used])
    if not saved:
        saved = "(no reply)"
    db.add_message(conversation_id, "assistant", saved)
    background.add_task(_learn, conversation_id, payload.message, reply)

    return ChatResponse(
        conversation_id=conversation_id,
        message=reply or saved,
        title=title,
        actions=tools_used,
        pending=pending,
    )


def _sse(event: str, data: dict) -> str:
    """Format one Server-Sent Event frame."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/chat/stream")
def chat_stream(payload: ChatRequest, background: BackgroundTasks):
    """Send a message and stream the reply, including any action steps."""
    conversation_id, title, history, extra_context = _prepare_turn(payload)

    def event_generator():
        yield _sse("start", {"conversation_id": conversation_id, "title": title})

        collected, tool_lines = [], []
        failed = None

        try:
            routed = _fast_path(payload.message)

            # One rendering loop for all three sources, so a fast-path
            # command and a model reply look identical in the browser.
            if routed is not None:
                source = agent.run_routed(routed, conversation_id)
            elif _use_agent():
                source = agent.run_agent(history, extra_context, conversation_id)
            else:
                source = (
                    {"type": "text", "text": piece}
                    for piece in ai_service.stream(history, extra_context=extra_context)
                )

            for event in source:
                kind = event["type"]
                if kind == "text":
                    collected.append(event["text"])
                    yield _sse("token", {"text": event["text"]})
                elif kind == "tool":
                    tool_lines.append(event["detail"])
                    yield _sse("tool", {
                        "name": event["name"],
                        "detail": event["detail"],
                        "result": event["result"],
                    })
                elif kind == "confirm":
                    yield _sse("confirm", {
                        "token": event["token"],
                        "detail": event["detail"],
                        "name": event["name"],
                        "risk": event.get("risk", ""),
                        "reason": event.get("reason", ""),
                    })
                elif kind == "error":
                    failed = event["detail"]

        except AIServiceError as exc:
            logger.warning("Stream aborted: %s", exc.user_message)
            failed = exc.user_message
        except Exception:  # noqa: BLE001
            logger.exception("Unexpected streaming failure")
            failed = "Sorry, something went wrong. Please try again."

        reply = "".join(collected).strip()
        saved = _transcript(reply, tool_lines)

        if saved:
            db.add_message(conversation_id, "assistant", saved)
            background.add_task(_learn, conversation_id, payload.message, reply)

        if failed:
            yield _sse("error", {"detail": failed})
            return
        if not saved:
            yield _sse("error", {"detail": "The AI returned an empty response. "
                                           "Please try again."})
            return

        yield _sse("done", {"conversation_id": conversation_id, "title": title})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
