"""
Security and permission layer.

EVERY tool call passes through evaluate() before it runs. Nothing bypasses it.

Three things decide what happens:

  1. RISK LEVEL   how much damage the tool could do
  2. CAPABILITY   the on/off switch the user controls in Settings
  3. POLICY       rules that cannot be turned off

Invariants that are enforced in code and covered by tests:

  * SENSITIVE and DESTRUCTIVE tools ALWAYS require confirmation. The user can
    make things stricter, never looser.
  * A tool that is not in the registry is denied. There is no "run any
    command" escape hatch, so the model cannot invent one.
  * A disabled capability is denied before any argument is even looked at.
  * Audit entries are scrubbed of anything that looks like a secret.
"""

import logging
import re
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional

from app.config import settings
from app.database import db

logger = logging.getLogger(__name__)


class Risk(IntEnum):
    """How dangerous a tool is. Higher means more caution."""

    SAFE = 0         # read-only, no side effects  (time, list files, read file)
    MODERATE = 1     # visible but easily undone   (create file, open an app)
    SENSITIVE = 2    # privacy / external / sending (screenshot, messaging)
    DESTRUCTIVE = 3  # data loss / system / money   (delete, move, git push)


# Anything at or above this level always asks the user first. Not configurable.
ALWAYS_CONFIRM_AT = Risk.SENSITIVE


@dataclass
class Capability:
    """A switch the user can flip in Settings."""

    key: str
    label: str
    description: str
    default_enabled: bool = True


CAPABILITIES = {
    "files": Capability(
        "files", "Files",
        "Create, read, search, move and delete files inside the Nova workspace."),
    "pc_control": Capability(
        "pc_control", "PC control",
        "Open applications on this computer."),
    "web": Capability(
        "web", "Web",
        "Open websites in your browser."),
    "git": Capability(
        "git", "Git",
        "Run git commands in your project folder."),
    "system": Capability(
        "system", "System info",
        "Read the time, disk space and computer details."),
    "media": Capability(
        "media", "Volume & media",
        "Change the volume and control whatever music or video is playing."),
    "screen": Capability(
        "screen", "Screen",
        "Take screenshots and see which windows are open. Privacy sensitive.",
        default_enabled=False),
    "messaging": Capability(
        "messaging", "Messaging",
        "Open WhatsApp, Telegram, Messenger, Instagram or email with a draft "
        "ready. Nova never presses Send for you."),
    "scheduler": Capability(
        "scheduler", "Reminders",
        "Set reminders and scheduled tasks."),
}


@dataclass
class Decision:
    """The verdict for one tool call."""

    outcome: str              # "allow" | "confirm" | "deny"
    risk: Risk
    capability: str
    reason: str = ""

    @property
    def allowed(self) -> bool:
        return self.outcome == "allow"

    @property
    def needs_confirmation(self) -> bool:
        return self.outcome == "confirm"

    @property
    def denied(self) -> bool:
        return self.outcome == "deny"


# --------------------------------------------------------------------------
# Permission storage
# --------------------------------------------------------------------------
def all_permissions() -> dict:
    """Every capability with its current state, filling in defaults."""
    stored = {row["capability"]: row for row in db.list_permissions()}
    result = {}
    for key, cap in CAPABILITIES.items():
        row = stored.get(key)
        result[key] = {
            "key": key,
            "label": cap.label,
            "description": cap.description,
            "enabled": bool(row["enabled"]) if row else cap.default_enabled,
            "always_ask": bool(row["always_ask"]) if row else False,
        }
    return result


def capability_enabled(key: str) -> bool:
    perms = all_permissions()
    if key not in perms:
        return False
    return perms[key]["enabled"]


def set_permission(key: str, enabled: bool, always_ask: bool = False) -> dict:
    if key not in CAPABILITIES:
        raise KeyError(f"Unknown capability: {key}")
    db.set_permission(key, enabled, always_ask)
    logger.info("Permission changed: %s enabled=%s always_ask=%s",
                key, enabled, always_ask)
    return all_permissions()[key]


# --------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------
def evaluate(tool_name: str, arguments: dict = None) -> Decision:
    """
    Decide whether a tool may run. Called before EVERY tool execution.

    Returns a Decision; the caller must honour it.
    """
    from app.services import actions  # imported here to avoid a circular import

    arguments = arguments or {}
    spec = actions.REGISTRY.get(tool_name)

    # 1. Unknown tool -> denied. This is what stops invented tools such as
    #    "run_shell" or "execute_command" from ever working.
    if spec is None:
        return Decision("deny", Risk.DESTRUCTIVE, "unknown",
                        f"'{tool_name}' is not one of my abilities.")

    risk: Risk = spec["risk"]
    capability: str = spec["capability"]

    # 2. Actions switched off entirely.
    if not settings.ACTIONS_ENABLED:
        return Decision("deny", risk, capability,
                        "Actions are switched off (ACTIONS_ENABLED=false).")

    # 3. Capability switched off by the user.
    perms = all_permissions()
    state = perms.get(capability)
    if state is None:
        return Decision("deny", risk, capability,
                        f"Unknown capability '{capability}'.")
    if not state["enabled"]:
        return Decision(
            "deny", risk, capability,
            f"The '{state['label']}' capability is turned off in Settings.")

    # 4. Risk-based confirmation. This cannot be disabled.
    if risk >= ALWAYS_CONFIRM_AT:
        return Decision("confirm", risk, capability,
                        f"{risk.name.title()} action needs your approval.")

    # 5. Per-tool escalation (git push is riskier than git status).
    escalate = spec.get("escalate")
    if callable(escalate) and escalate(arguments):
        return Decision("confirm", Risk.DESTRUCTIVE, capability,
                        "This changes things, so I need your approval.")

    # 6. The user asked to be consulted for this capability.
    if state["always_ask"]:
        return Decision("confirm", risk, capability,
                        f"You asked to approve every '{state['label']}' action.")

    # 7. Global "confirm everything" switch.
    if settings.ACTIONS_CONFIRM and risk >= Risk.MODERATE and settings.STRICT_CONFIRM:
        return Decision("confirm", risk, capability,
                        "Strict confirmation mode is on.")

    return Decision("allow", risk, capability, "Safe to run.")


# --------------------------------------------------------------------------
# Audit logging (secret-scrubbed)
# --------------------------------------------------------------------------
SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{8,}"),
    re.compile(r"(?i)\b(api[_-]?key|token|password|passwd|secret)\b\s*[:=]\s*\S+"),
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),  # emails
]


def scrub(value):
    """Remove anything that looks like a credential before it is logged."""
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    if not isinstance(value, str):
        return value

    cleaned = value
    for pattern in SECRET_PATTERNS:
        cleaned = pattern.sub("[redacted]", cleaned)
    return cleaned


def describe_policy() -> dict:
    """Shown in Settings so the rules are visible, not hidden in code."""
    return {
        "risk_levels": [
            {"name": r.name, "value": int(r),
             "behaviour": "runs immediately" if r < ALWAYS_CONFIRM_AT
                          else "always asks first"}
            for r in Risk
        ],
        "always_confirm_at": ALWAYS_CONFIRM_AT.name,
        "shell_access": "never - there is no arbitrary command tool",
        "filesystem": str(settings.NOVA_WORKSPACE),
    }
