"""
Phase 3/4/5 tools: PC control, web search, communication and media.

Kept in a separate module so the original file stays readable. Everything
registers into the same REGISTRY, so every tool here goes through exactly the
same security gate as the file tools.

Risk choices worth explaining:

* Screenshots and window titles are SENSITIVE, not moderate. They reveal
  whatever is on screen, which may be a bank page or a private chat.
* Every messaging tool is SENSITIVE because it involves other people. Nova
  only ever opens a draft; the user presses Send.
* Volume and media keys are MODERATE: visible, instantly reversible, and
  needing a confirmation click to pause music would be miserable.
"""

import logging

from app.services import comms, pc_control, web
from app.services.actions import ActionError, REGISTRY
from app.services.security import Risk

logger = logging.getLogger(__name__)


def _wrap(fn, *args, **kwargs) -> str:
    """Run a helper and turn its private exception into an ActionError."""
    try:
        return fn(*args, **kwargs)
    except (pc_control.ControlError, comms.CommsError, web.WebError) as exc:
        raise ActionError(str(exc)) from exc


# --------------------------------------------------------------------------
# Thin adapters
# --------------------------------------------------------------------------
def act_volume_up(steps: int = 5) -> str:
    return _wrap(pc_control.volume_up, steps)


def act_volume_down(steps: int = 5) -> str:
    return _wrap(pc_control.volume_down, steps)


def act_volume_mute() -> str:
    return _wrap(pc_control.volume_mute)


def act_media_play_pause() -> str:
    return _wrap(pc_control.media_play_pause)


def act_media_next() -> str:
    return _wrap(pc_control.media_next)


def act_media_previous() -> str:
    return _wrap(pc_control.media_previous)


def act_screenshot(name: str = "") -> str:
    return _wrap(pc_control.take_screenshot, name)


def act_list_windows() -> str:
    return _wrap(pc_control.list_windows)


def act_play_music(query: str = "", service: str = "youtube") -> str:
    return _wrap(comms.play_music, query, service)


def act_whatsapp(number: str = "", message: str = "") -> str:
    return _wrap(comms.whatsapp, number, message)


def act_telegram(username: str = "", message: str = "") -> str:
    return _wrap(comms.telegram, username, message)


def act_messenger(person: str = "") -> str:
    return _wrap(comms.messenger, person)


def act_instagram(person: str = "") -> str:
    return _wrap(comms.instagram, person)


def act_email_draft(to: str = "", subject: str = "", body: str = "") -> str:
    return _wrap(comms.email_draft, to, subject, body)


def act_web_search(query: str = "", count: int = 5) -> str:
    return _wrap(web.search, query, count)


def _whatsapp_phrase(a: dict) -> str:
    who = a.get("number") or "a chat"
    text = a.get("message")
    return f"Open WhatsApp to {who}" + (f' with: "{text}"' if text else "")


# --------------------------------------------------------------------------
# Registration
# --------------------------------------------------------------------------
EXTRA_TOOLS = {
    # ---------------- Phase 3: PC control ----------------
    "volume_up": {
        "fn": act_volume_up, "risk": Risk.MODERATE, "capability": "media",
        "description": "Turn the computer volume up.",
        "params": {"steps": {"type": "integer", "description": "How many steps, 1-20."}},
        "required": [],
        "phrase": lambda a: "Turn the volume up",
    },
    "volume_down": {
        "fn": act_volume_down, "risk": Risk.MODERATE, "capability": "media",
        "description": "Turn the computer volume down.",
        "params": {"steps": {"type": "integer", "description": "How many steps, 1-20."}},
        "required": [],
        "phrase": lambda a: "Turn the volume down",
    },
    "volume_mute": {
        "fn": act_volume_mute, "risk": Risk.MODERATE, "capability": "media",
        "description": "Mute or unmute the computer.",
        "params": {}, "required": [],
        "phrase": lambda a: "Mute / unmute",
    },
    "media_play_pause": {
        "fn": act_media_play_pause, "risk": Risk.MODERATE, "capability": "media",
        "description": "Play or pause the current music or video.",
        "params": {}, "required": [],
        "phrase": lambda a: "Play / pause",
    },
    "media_next": {
        "fn": act_media_next, "risk": Risk.MODERATE, "capability": "media",
        "description": "Skip to the next track.",
        "params": {}, "required": [],
        "phrase": lambda a: "Next track",
    },
    "media_previous": {
        "fn": act_media_previous, "risk": Risk.MODERATE, "capability": "media",
        "description": "Go back to the previous track.",
        "params": {}, "required": [],
        "phrase": lambda a: "Previous track",
    },
    "take_screenshot": {
        "fn": act_screenshot, "risk": Risk.SENSITIVE, "capability": "screen",
        "description": "Capture the screen and save it to the Nova workspace. "
                       "Privacy sensitive: always asks first.",
        "params": {"name": {"type": "string", "description": "Optional file name."}},
        "required": [],
        "phrase": lambda a: "Take a screenshot of your screen",
    },
    "list_windows": {
        "fn": act_list_windows, "risk": Risk.SENSITIVE, "capability": "screen",
        "description": "List the titles of open windows.",
        "params": {}, "required": [],
        "phrase": lambda a: "See which windows are open",
    },

    # ---------------- Phase 4: web ----------------
    "web_search": {
        "fn": act_web_search, "risk": Risk.MODERATE, "capability": "web",
        "description": "Search the web for current information and return the "
                       "top results. Use this for news, prices, or anything "
                       "that may have changed recently.",
        "params": {
            "query": {"type": "string", "description": "What to search for."},
            "count": {"type": "integer", "description": "How many results, 1-8."},
        },
        "required": ["query"],
        "phrase": lambda a: "Search the web for " + str(a.get("query", "")),
    },

    # ---------------- Phase 5: media + communication ----------------
    "play_music": {
        "fn": act_play_music, "risk": Risk.MODERATE, "capability": "media",
        "description": "Find and open a song on YouTube, YouTube Music or Spotify.",
        "params": {
            "query": {"type": "string", "description": "Song or artist."},
            "service": {"type": "string", "description": "youtube, ytmusic or spotify."},
        },
        "required": [],
        "phrase": lambda a: "Play " + str(a.get("query") or "music"),
    },
    "whatsapp": {
        "fn": act_whatsapp, "risk": Risk.SENSITIVE, "capability": "messaging",
        "description": "Open a WhatsApp chat with a message pre-typed. The user "
                       "presses Send; you never send it yourself.",
        "params": {
            "number": {"type": "string", "description": "Phone number with country code."},
            "message": {"type": "string", "description": "Message text to pre-fill."},
        },
        "required": [],
        "phrase": lambda a: _whatsapp_phrase(a),
    },
    "telegram": {
        "fn": act_telegram, "risk": Risk.SENSITIVE, "capability": "messaging",
        "description": "Open Telegram, optionally at a specific person.",
        "params": {
            "username": {"type": "string", "description": "Telegram @username."},
            "message": {"type": "string", "description": "Message text to pre-fill."},
        },
        "required": [],
        "phrase": lambda a: "Open Telegram",
    },
    "messenger": {
        "fn": act_messenger, "risk": Risk.SENSITIVE, "capability": "messaging",
        "description": "Open Facebook Messenger, optionally at a specific person.",
        "params": {"person": {"type": "string", "description": "Messenger username."}},
        "required": [],
        "phrase": lambda a: "Open Messenger",
    },
    "instagram": {
        "fn": act_instagram, "risk": Risk.SENSITIVE, "capability": "messaging",
        "description": "Open Instagram, a profile, or your direct messages.",
        "params": {"person": {"type": "string", "description": "Instagram username."}},
        "required": [],
        "phrase": lambda a: "Open Instagram",
    },
    "email_draft": {
        "fn": act_email_draft, "risk": Risk.SENSITIVE, "capability": "messaging",
        "description": "Open the mail app with a draft ready. Nothing is sent.",
        "params": {
            "to": {"type": "string", "description": "Recipient address."},
            "subject": {"type": "string", "description": "Subject line."},
            "body": {"type": "string", "description": "Message body."},
        },
        "required": [],
        "phrase": lambda a: "Draft an email to " + str(a.get("to") or "someone"),
    },
}

REGISTRY.update(EXTRA_TOOLS)
logger.info("Registered %s extra tools (total %s)", len(EXTRA_TOOLS), len(REGISTRY))
