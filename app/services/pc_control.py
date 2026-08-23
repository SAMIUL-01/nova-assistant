"""
Phase 3 - PC control: volume, media keys, screenshots, window titles.

Design notes:

* Volume and media keys are sent with plain `ctypes` on Windows. No extra
  dependency, no admin rights, and it works with whatever is playing:
  Spotify, YouTube in a browser, VLC, anything that listens to media keys.
* Everything degrades honestly. On Linux and macOS the Windows-only calls
  return a clear "not supported here" message instead of pretending to work.
* Screenshots are PRIVACY SENSITIVE. The tool is classified accordingly and
  always asks before capturing, and images land in the Nova workspace so the
  user can see and delete them.
"""

import logging
import platform
import subprocess
import time
from datetime import datetime
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


class ControlError(Exception):
    """A PC-control action that could not be performed. Safe to show."""


def _os() -> str:
    system = platform.system().lower()
    if system.startswith("win"):
        return "win"
    if system == "darwin":
        return "mac"
    return "linux"


IS_WINDOWS = _os() == "win"


# --------------------------------------------------------------------------
# Windows virtual key codes for the media/volume keys on a keyboard
# --------------------------------------------------------------------------
VK = {
    "volume_mute": 0xAD,
    "volume_down": 0xAE,
    "volume_up": 0xAF,
    "media_next": 0xB0,
    "media_previous": 0xB1,
    "media_stop": 0xB2,
    "media_play_pause": 0xB3,
}

KEYEVENTF_KEYUP = 0x0002


def _tap_key(code: int, times: int = 1) -> None:
    """Press and release a virtual key, Windows only."""
    if not IS_WINDOWS:
        raise ControlError(
            "Volume and media keys are only supported when Nova runs on Windows."
        )
    import ctypes

    user32 = ctypes.windll.user32
    for _ in range(max(1, times)):
        user32.keybd_event(code, 0, 0, 0)
        user32.keybd_event(code, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.02)


# --------------------------------------------------------------------------
# Volume
# --------------------------------------------------------------------------
def volume_up(steps: int = 5) -> str:
    steps = max(1, min(int(steps or 5), 20))
    _tap_key(VK["volume_up"], steps)
    return f"Turned the volume up {steps} step(s)."


def volume_down(steps: int = 5) -> str:
    steps = max(1, min(int(steps or 5), 20))
    _tap_key(VK["volume_down"], steps)
    return f"Turned the volume down {steps} step(s)."


def volume_mute() -> str:
    _tap_key(VK["volume_mute"])
    return "Toggled mute."


# --------------------------------------------------------------------------
# Media transport
# --------------------------------------------------------------------------
def media_play_pause() -> str:
    _tap_key(VK["media_play_pause"])
    return "Play/pause sent to whatever is playing."


def media_next() -> str:
    _tap_key(VK["media_next"])
    return "Skipped to the next track."


def media_previous() -> str:
    _tap_key(VK["media_previous"])
    return "Went back to the previous track."


def media_stop() -> str:
    _tap_key(VK["media_stop"])
    return "Stopped playback."


# --------------------------------------------------------------------------
# Screenshot  (privacy sensitive - always confirmed)
# --------------------------------------------------------------------------
def take_screenshot(name: str = "") -> str:
    """Capture the screen into the Nova workspace."""
    try:
        from PIL import ImageGrab
    except ImportError as exc:  # pragma: no cover
        raise ControlError("Screenshots need the Pillow package.") from exc

    try:
        image = ImageGrab.grab()
    except Exception as exc:  # noqa: BLE001  (headless Linux, permissions, ...)
        raise ControlError(
            "I could not capture the screen on this system."
        ) from exc

    folder = settings.NOVA_WORKSPACE.expanduser() / "screenshots"
    folder.mkdir(parents=True, exist_ok=True)

    safe = "".join(c for c in (name or "") if c.isalnum() or c in "-_ ").strip()
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    filename = f"{safe or 'screen'}-{stamp}.png"
    path = folder / filename
    image.save(path)

    return (f"Saved a screenshot to screenshots/{filename} "
            f"({image.width}x{image.height}).")


# --------------------------------------------------------------------------
# Windows / running apps
# --------------------------------------------------------------------------
def list_windows() -> str:
    """List the titles of open windows."""
    if IS_WINDOWS:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        titles = []

        WNDENUMPROC = ctypes.WINFUNCTYPE(
            wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def callback(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            text = buffer.value.strip()
            if text:
                titles.append(text)
            return True

        user32.EnumWindows(WNDENUMPROC(callback), 0)
        if not titles:
            return "No visible windows found."
        shown = titles[:30]
        more = "" if len(titles) <= 30 else f"\n...and {len(titles) - 30} more"
        return "Open windows:\n" + "\n".join(f"- {t}" for t in shown) + more

    if _os() == "mac":
        try:
            out = subprocess.run(
                ["osascript", "-e",
                 'tell application "System Events" to get name of '
                 '(processes where background only is false)'],
                capture_output=True, text=True, timeout=15)
            return "Open apps:\n" + out.stdout.strip()
        except Exception as exc:  # noqa: BLE001
            raise ControlError("Could not list windows.") from exc

    raise ControlError("Listing windows is not supported on this system.")


def capabilities_report() -> dict:
    """What actually works on this machine, so the UI can be honest."""
    return {
        "os": platform.system(),
        "volume_and_media_keys": IS_WINDOWS,
        "screenshots": True,
        "window_list": IS_WINDOWS or _os() == "mac",
    }
