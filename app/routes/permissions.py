"""
Permission manager endpoints.

GET  /api/permissions        -> every capability, its state, and the policy
PUT  /api/permissions/{key}  -> turn a capability on/off, or make it always ask
POST /api/permissions/reset  -> back to defaults
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.database import db
from app.models.schemas import PermissionUpdate, SimpleResult
from app.services import security
from app.services.auth import require_login

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/permissions", tags=["permissions"],
                   dependencies=[Depends(require_login)])


@router.get("")
def list_permissions():
    """What Nova is allowed to do, and the rules that cannot be changed."""
    return {
        "capabilities": list(security.all_permissions().values()),
        "policy": security.describe_policy(),
        "tools": [
            {
                "name": name,
                "capability": spec["capability"],
                "risk": spec["risk"].name,
                "always_confirms": spec["risk"] >= security.ALWAYS_CONFIRM_AT,
                "description": spec["description"],
            }
            for name, spec in _registry().items()
        ],
    }


def _registry():
    from app.services import actions
    return actions.REGISTRY


@router.put("/{key}")
def update_permission(key: str, payload: PermissionUpdate):
    try:
        updated = security.set_permission(key, payload.enabled, payload.always_ask)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"No capability '{key}'.") from exc
    return updated


@router.post("/reset", response_model=SimpleResult)
def reset():
    db.reset_permissions()
    return SimpleResult(ok=True, detail="Permissions reset to defaults.")
