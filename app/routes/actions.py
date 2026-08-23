"""
Action endpoints: what Nova can do, and confirming risky actions.

GET    /api/actions            -> the list of abilities (for the UI)
POST   /api/actions/confirm    -> run a parked action after you press Confirm
POST   /api/actions/cancel     -> throw a parked action away
GET    /api/actions/log        -> recent action history
"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException

from app.config import settings
from app.database import db
from app.models.schemas import ActionToken, SimpleResult
from app.services import actions, agent, security
from app.services.auth import require_login

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/actions", tags=["actions"],
                   dependencies=[Depends(require_login)])


@router.get("")
def list_actions():
    """Everything Nova is allowed to do, for the help panel."""
    return {
        "enabled": settings.ACTIONS_ENABLED,
        "confirm_destructive": settings.ACTIONS_CONFIRM,
        "workspace": str(settings.NOVA_WORKSPACE),
        "abilities": [
            {
                "name": name,
                "description": spec["description"],
                "risk": spec["risk"].name,
                "capability": spec["capability"],
                "needs_confirmation": spec["risk"] >= security.ALWAYS_CONFIRM_AT,
            }
            for name, spec in actions.REGISTRY.items()
        ],
        "websites": sorted(actions.SITES),
        "apps": sorted(actions.APPS),
    }


@router.post("/confirm")
def confirm(payload: ActionToken):
    """The user pressed Confirm: actually perform the action now."""
    try:
        outcome = agent.confirm_and_run(payload.token)
    except actions.ActionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Keep the transcript honest by recording what happened.
    conversation_id = outcome.get("conversation_id")
    if conversation_id and db.conversation_exists(conversation_id):
        db.add_message(conversation_id, "assistant", f"✅ {outcome['result']}")

    return outcome


@router.post("/cancel", response_model=SimpleResult)
def cancel(payload: ActionToken):
    agent.cancel_pending(payload.token)
    return SimpleResult(ok=True, detail="Cancelled. I did not do it.")


@router.get("/log")
def action_log(limit: int = 50):
    """The last few actions Nova attempted, newest first."""
    path = settings.ACTION_LOG
    if not path.exists():
        return {"entries": []}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {"entries": []}

    entries = []
    for line in lines[-max(1, min(limit, 500)):]:
        try:
            entries.append(json.loads(line))
        except ValueError:
            continue
    entries.reverse()
    return {"entries": entries}
