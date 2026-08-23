"""
The agent loop: let the model call actions, then keep talking.

Flow for one user message:

    model  ->  "I want to run open_website(youtube)"
    Nova   ->  runs it (or asks you to confirm first)
    model  ->  "Opened YouTube for you."

Everything is streamed to the browser as it happens, so you see each step.
Confirmation-required actions are parked as "pending" until you press Confirm.
"""

import json
import logging
import secrets
import time
from typing import Dict, Iterator

from app.config import settings
from app.services import actions, security
from app.services.ai_service import AIServiceError, ai_service, _friendly_error

logger = logging.getLogger(__name__)

# token -> pending action waiting for the user's Confirm button
_PENDING: Dict[str, dict] = {}
PENDING_TTL_SECONDS = 900


def _cleanup_pending() -> None:
    now = time.time()
    for token in [t for t, p in _PENDING.items() if now - p["created"] > PENDING_TTL_SECONDS]:
        _PENDING.pop(token, None)


def park_action(name: str, arguments: dict, conversation_id: int) -> str:
    """Store an action until the user confirms it, and return its token."""
    _cleanup_pending()
    token = secrets.token_urlsafe(16)
    _PENDING[token] = {
        "name": name,
        "arguments": arguments,
        "conversation_id": conversation_id,
        "created": time.time(),
    }
    return token


def take_pending(token: str) -> dict:
    """Pop a parked action, or raise if it is unknown/expired."""
    _cleanup_pending()
    pending = _PENDING.pop(token, None)
    if pending is None:
        raise actions.ActionError(
            "That request expired or was already handled. Please ask me again."
        )
    return pending


def cancel_pending(token: str) -> bool:
    return _PENDING.pop(token, None) is not None


# --------------------------------------------------------------------------
def _accumulate_tool_calls(delta, store: Dict[int, dict]) -> None:
    """Rebuild tool calls that arrive split across many streamed chunks."""
    for tc in getattr(delta, "tool_calls", None) or []:
        slot = store.setdefault(tc.index, {"id": "", "name": "", "args": ""})
        if tc.id:
            slot["id"] = tc.id
        fn = getattr(tc, "function", None)
        if fn is not None:
            if fn.name:
                slot["name"] += fn.name
            if fn.arguments:
                slot["args"] += fn.arguments


def _parse_args(raw: str) -> dict:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, TypeError):
        return {}


def run_agent(history: list, extra_context: str, conversation_id: int) -> Iterator[dict]:
    """
    Yield events while the model works:

        {"type": "text",    "text": "..."}            reply text, token by token
        {"type": "tool",    "name": ..., "detail": ..., "result": ...}
        {"type": "confirm", "token": ..., "detail": ...}
        {"type": "error",   "detail": ...}
    """
    # Offline mock mode: no provider, so no tools either.
    if settings.AI_OFFLINE_MOCK:
        for chunk in ai_service.stream(history, extra_context=extra_context):
            yield {"type": "text", "text": chunk}
        return

    context = extra_context
    note = actions.system_prompt_note()
    if note:
        context = f"{context}\n\n{note}" if context else note

    messages = ai_service.build_messages(history, context)
    tools = actions.tool_schemas()
    awaiting_confirmation = False

    for round_number in range(settings.MAX_TOOL_ROUNDS):
        text_parts: list = []
        calls: Dict[int, dict] = {}

        try:
            stream = ai_service.client.chat.completions.create(
                model=ai_service.model,
                messages=messages,
                tools=tools,
                temperature=settings.AI_TEMPERATURE,
                max_tokens=settings.AI_MAX_TOKENS,
                stream=True,
            )
            for event in stream:
                if not getattr(event, "choices", None):
                    continue
                delta = getattr(event.choices[0], "delta", None)
                if delta is None:
                    continue
                if getattr(delta, "content", None):
                    text_parts.append(delta.content)
                    yield {"type": "text", "text": delta.content}
                _accumulate_tool_calls(delta, calls)
        except AIServiceError as exc:
            yield {"type": "error", "detail": exc.user_message}
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception("Agent round %s failed", round_number)
            yield {"type": "error", "detail": _friendly_error(exc)}
            return

        if not calls:
            return                      # the model is done talking

        # Record what the model asked for.
        ordered = [calls[i] for i in sorted(calls)]
        messages.append({
            "role": "assistant",
            "content": "".join(text_parts) or None,
            "tool_calls": [
                {
                    "id": c["id"] or f"call_{i}",
                    "type": "function",
                    "function": {"name": c["name"], "arguments": c["args"] or "{}"},
                }
                for i, c in enumerate(ordered)
            ],
        })

        # Run them (or park them for confirmation).
        for i, call in enumerate(ordered):
            name = call["name"]
            args = _parse_args(call["args"])
            call_id = call["id"] or f"call_{i}"
            detail = actions.describe(name, args)

            decision = security.evaluate(name, args)

            # Blocked outright: unknown tool, or a capability switched off.
            if decision.denied:
                actions.audit(name, args, f"DENIED: {decision.reason}",
                              decision.risk.name, "deny")
                yield {"type": "tool", "name": name, "detail": detail,
                       "result": f"Not allowed: {decision.reason}"}
                messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": f"REFUSED: {decision.reason} "
                               "Tell the user, and do not try again.",
                })
                continue

            # Needs the user's approval first.
            if decision.needs_confirmation:
                token = park_action(name, args, conversation_id)
                awaiting_confirmation = True
                yield {"type": "confirm", "token": token, "detail": detail,
                       "name": name, "risk": decision.risk.name,
                       "reason": decision.reason}
                messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": "Waiting for the user to press Confirm. "
                               "Do not retry this action. Tell the user you need "
                               "their confirmation.",
                })
                continue

            try:
                result = actions.execute(name, args)
                yield {"type": "tool", "name": name, "detail": detail, "result": result}
            except actions.ActionError as exc:
                result = f"Failed: {exc}"
                yield {"type": "tool", "name": name, "detail": detail, "result": result}

            messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": result[:4000],
            })

        if awaiting_confirmation:
            # Let the model say one closing sentence, then stop.
            tools = []      # no more tool calls this turn

    logger.info("Agent stopped after %s rounds", settings.MAX_TOOL_ROUNDS)


def run_routed(command, conversation_id: int) -> Iterator[dict]:
    """
    Execute a command the router understood, with no model call at all.

    Emits the same events as run_agent so the browser renders it identically,
    and still goes through the security layer.
    """
    name, args = command.tool, command.arguments
    detail = actions.describe(name, args)
    decision = security.evaluate(name, args)

    if decision.denied:
        actions.audit(name, args, f"DENIED: {decision.reason}",
                      decision.risk.name, "deny")
        yield {"type": "text", "text": decision.reason}
        return

    if decision.needs_confirmation:
        token = park_action(name, args, conversation_id)
        yield {"type": "text", "text": "That one needs your approval first."}
        yield {"type": "confirm", "token": token, "detail": detail,
               "name": name, "risk": decision.risk.name, "reason": decision.reason}
        return

    # Say something immediately: this is what makes voice feel instant.
    yield {"type": "text", "text": command.spoken}
    try:
        result = actions.execute(name, args)
        yield {"type": "tool", "name": name, "detail": detail, "result": result}
    except actions.ActionError as exc:
        yield {"type": "tool", "name": name, "detail": detail,
               "result": f"Failed: {exc}"}


def confirm_and_run(token: str) -> dict:
    """Execute a parked action after the user pressed Confirm."""
    pending = take_pending(token)
    name, args = pending["name"], pending["arguments"]

    # The user approving does not bypass a disabled capability.
    decision = security.evaluate(name, args)
    if decision.denied:
        raise actions.ActionError(decision.reason)

    result = actions.execute(name, args, _approved=True)
    return {
        "name": name,
        "detail": actions.describe(name, args),
        "result": result,
        "conversation_id": pending["conversation_id"],
    }
