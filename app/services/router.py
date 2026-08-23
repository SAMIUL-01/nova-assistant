"""
Command router: the single pipeline that both typed and spoken commands use.

Why this exists: sending "open youtube" to the language model costs a network
round trip and a second or two. For a voice assistant that feels slow. The
router recognises a small set of very common commands and turns them straight
into a tool call. Everything else falls through to the model, which is the
normal path.

Text and voice hit exactly the same function, so the two can never drift
apart. Voice input is just text that arrived from a microphone.

Fast paths never skip security: the result is still a tool call that goes
through security.evaluate() before running.
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional

from app.services import actions

logger = logging.getLogger(__name__)


@dataclass
class RoutedCommand:
    """A command the router understood without asking the model."""

    tool: str
    arguments: dict
    spoken: str          # what Nova says while doing it


# --------------------------------------------------------------------------
# Patterns. Bangla/Banglish included, because that is how the user talks.
# --------------------------------------------------------------------------
def _site_pattern() -> str:
    return "|".join(sorted((re.escape(s) for s in actions.SITES), key=len, reverse=True))


def _app_pattern() -> str:
    return "|".join(sorted((re.escape(a) for a in actions.APPS), key=len, reverse=True))


RULES = [
    # --- open a website -------------------------------------------------
    (rf"^(?:please\s+)?(?:open|khulo|khule\s+dao|chalu\s+koro|launch|go\s+to)\s+"
     rf"(?P<site>{_site_pattern()})\b.*$",
     lambda m: RoutedCommand("open_website", {"site": m.group("site")},
                             f"Opening {m.group('site').title()}.")),

    # --- open an application ---------------------------------------------
    (rf"^(?:please\s+)?(?:open|launch|start|chalu\s+koro)\s+"
     rf"(?P<app>{_app_pattern()})\b.*$",
     lambda m: RoutedCommand("open_app", {"name": m.group("app")},
                             f"Opening {m.group('app')}.")),

    # --- time -------------------------------------------------------------
    (r"^(?:what(?:'s| is)\s+the\s+time|what\s+time\s+is\s+it|koyta\s+baje|"
     r"time\s+koto|current\s+time)\??$",
     lambda m: RoutedCommand("current_time", {}, "Checking the time.")),

    # --- system info -------------------------------------------------------
    (r"^(?:system\s+info(?:rmation)?|pc\s+info|computer\s+info|"
     r"how\s+much\s+disk\s+space)\??$",
     lambda m: RoutedCommand("system_info", {}, "Checking your system.")),

    # --- list files --------------------------------------------------------
    (r"^(?:list|show|dekhao)\s+(?:my\s+)?files?(?:\s+in\s+(?P<path>[\w\-./ ]+))?\s*$",
     lambda m: RoutedCommand("list_files", {"path": (m.group("path") or ".").strip()},
                             "Listing your files.")),
]

COMPILED = [(re.compile(pattern, re.IGNORECASE), build) for pattern, build in RULES]


def route(message: str) -> Optional[RoutedCommand]:
    """
    Try to understand the command without the model.

    Returns None when the model should handle it, which is the common case.
    Deliberately conservative: a wrong fast path is worse than a slow one.
    """
    text = (message or "").strip().rstrip(".!")
    if not text or len(text) > 120:      # long sentences are for the model
        return None

    for pattern, build in COMPILED:
        match = pattern.match(text)
        if match:
            try:
                command = build(match)
            except Exception:  # noqa: BLE001
                logger.exception("Router rule failed on: %s", text)
                return None
            logger.info("Router fast path: %r -> %s", text, command.tool)
            return command
    return None
