"""
Phase 5 - Communication and media.

An important design decision: Nova does NOT drive WhatsApp Web with a
headless browser. That approach breaks every time Meta changes their HTML,
it can get an account flagged, and it makes it easy to send a message the
user never actually saw.

Instead Nova opens the real app or web client with the message already typed
in, and the user presses Send. One extra keypress, and it works reliably
forever. Nova never sends anything on its own.

Every function here is classified SENSITIVE because it touches other people.
"""

import logging
import urllib.parse
import webbrowser

logger = logging.getLogger(__name__)


class CommsError(Exception):
    """A communication action that could not be performed. Safe to show."""


def _clean_phone(number: str) -> str:
    """Keep digits only; WhatsApp wants the country code without symbols."""
    digits = "".join(c for c in (number or "") if c.isdigit())
    if len(digits) < 8:
        raise CommsError(
            "That does not look like a full phone number. "
            "Include the country code, for example 8801712345678."
        )
    return digits


# --------------------------------------------------------------------------
# WhatsApp
# --------------------------------------------------------------------------
def whatsapp(number: str = "", message: str = "") -> str:
    """
    Open a WhatsApp chat, with the message pre-typed.

    The user still presses Send. Nova never sends it silently.
    """
    text = urllib.parse.quote(message or "")

    if number:
        phone = _clean_phone(number)
        url = f"https://wa.me/{phone}" + (f"?text={text}" if text else "")
        who = f"+{phone}"
    else:
        if not message:
            raise CommsError("Tell me who to message, or what to say.")
        url = f"https://wa.me/?text={text}"
        who = "WhatsApp"

    webbrowser.open(url)
    if message:
        return (f"Opened WhatsApp for {who} with your message ready. "
                "Press Send when you are happy with it.")
    return f"Opened WhatsApp for {who}."


# --------------------------------------------------------------------------
# Telegram
# --------------------------------------------------------------------------
def telegram(username: str = "", message: str = "") -> str:
    text = urllib.parse.quote(message or "")
    handle = (username or "").lstrip("@").strip()

    if handle:
        url = f"https://t.me/{handle}"
        if text:
            url = f"https://t.me/share/url?url=&text={text}"
        who = f"@{handle}"
    else:
        url = "https://web.telegram.org"
        who = "Telegram"

    webbrowser.open(url)
    return f"Opened Telegram for {who}."


# --------------------------------------------------------------------------
# Messenger / Instagram
# --------------------------------------------------------------------------
def messenger(person: str = "") -> str:
    handle = (person or "").strip().lstrip("@")
    url = f"https://www.messenger.com/t/{urllib.parse.quote(handle)}" if handle \
        else "https://www.messenger.com"
    webbrowser.open(url)
    return f"Opened Messenger{f' for {handle}' if handle else ''}."


def instagram(person: str = "") -> str:
    handle = (person or "").strip().lstrip("@")
    if handle:
        url = f"https://www.instagram.com/{urllib.parse.quote(handle)}/"
        what = f"{handle}'s profile"
    else:
        url = "https://www.instagram.com/direct/inbox/"
        what = "your Instagram inbox"
    webbrowser.open(url)
    return f"Opened {what}."


def email_draft(to: str = "", subject: str = "", body: str = "") -> str:
    """Open the default mail app with a draft ready. Nothing is sent."""
    params = {}
    if subject:
        params["subject"] = subject
    if body:
        params["body"] = body
    query = ("?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)) \
        if params else ""
    webbrowser.open(f"mailto:{to}{query}")
    return (f"Opened a draft email{f' to {to}' if to else ''}. "
            "Nothing is sent until you press Send yourself.")


# --------------------------------------------------------------------------
# Music
# --------------------------------------------------------------------------
def play_music(query: str = "", service: str = "youtube") -> str:
    """Search for a song and open it, ready to play."""
    song = (query or "").strip()
    provider = (service or "youtube").strip().lower()

    if not song:
        webbrowser.open("https://music.youtube.com")
        return "Opened YouTube Music."

    encoded = urllib.parse.quote(song)
    if provider in ("spotify", "spot"):
        url = f"https://open.spotify.com/search/{encoded}"
        where = "Spotify"
    elif provider in ("youtube music", "ytmusic", "music"):
        url = f"https://music.youtube.com/search?q={encoded}"
        where = "YouTube Music"
    else:
        # The classic trick: this opens the first video straight away.
        url = f"https://www.youtube.com/results?search_query={encoded}"
        where = "YouTube"

    webbrowser.open(url)
    return f"Searching {where} for '{song}'. Click the first result to play."
