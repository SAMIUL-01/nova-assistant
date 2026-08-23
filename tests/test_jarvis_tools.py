"""
Tests for the JARVIS tools added in phases 3, 4 and 5.

Focus: the URLs Nova builds, honest failure on unsupported systems, and the
promise that Nova never sends a message on its own.
"""

import os
import tempfile
from pathlib import Path

import pytest

WS = Path(tempfile.gettempdir()) / "nova_jarvis_ws"
TMP_DB = Path(tempfile.gettempdir()) / "nova_jarvis_test.db"

os.environ["AI_OFFLINE_MOCK"] = "1"
os.environ["DB_PATH"] = str(TMP_DB)
os.environ["RATE_LIMIT_PER_MINUTE"] = "1000"
os.environ["ACTIONS_ENABLED"] = "true"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import db  # noqa: E402
from app.database.db import init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services import actions, comms, pc_control, security, web  # noqa: E402
from app.services.security import Risk  # noqa: E402


@pytest.fixture(scope="module")
def client():
    if TMP_DB.exists():
        TMP_DB.unlink()
    WS.mkdir(parents=True, exist_ok=True)
    init_db()
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def clean(monkeypatch, client):
    from app.config import settings
    WS.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "NOVA_WORKSPACE", WS)
    monkeypatch.setattr(settings, "ACTION_LOG", WS / "actions.log")
    db.reset_permissions()
    yield
    db.reset_permissions()


@pytest.fixture
def opened(monkeypatch):
    """Capture URLs instead of really launching a browser."""
    urls = []
    monkeypatch.setattr(comms.webbrowser, "open", lambda u: urls.append(u))
    return urls


# ==========================================================================
# Phase 3 - PC control
# ==========================================================================
def test_media_tools_are_moderate_not_annoying():
    """Pausing music must not need a confirmation click."""
    for name in ["volume_up", "volume_down", "volume_mute",
                 "media_play_pause", "media_next", "media_previous"]:
        assert actions.REGISTRY[name]["risk"] == Risk.MODERATE
        assert security.evaluate(name, {}).allowed, f"{name} should just run"


def test_volume_fails_clearly_on_non_windows(monkeypatch):
    monkeypatch.setattr(pc_control, "IS_WINDOWS", False)
    with pytest.raises(pc_control.ControlError) as exc:
        pc_control.volume_up()
    assert "Windows" in str(exc.value)


def test_volume_sends_the_right_number_of_key_taps(monkeypatch):
    taps = []
    monkeypatch.setattr(pc_control, "_tap_key",
                        lambda code, times=1: taps.append((code, times)))
    pc_control.volume_up(3)
    assert taps == [(pc_control.VK["volume_up"], 3)]

    taps.clear()
    pc_control.media_next()
    assert taps == [(pc_control.VK["media_next"], 1)]


def test_volume_steps_are_clamped(monkeypatch):
    taps = []
    monkeypatch.setattr(pc_control, "_tap_key",
                        lambda code, times=1: taps.append(times))
    pc_control.volume_up(9999)
    pc_control.volume_down(-5)
    assert taps == [20, 1], "steps must be clamped to a sane range"


# --- screenshots are privacy sensitive ------------------------------------
def test_screen_capability_is_off_by_default():
    assert security.all_permissions()["screen"]["enabled"] is False
    assert security.evaluate("take_screenshot", {}).denied


def test_screenshot_requires_confirmation_even_when_enabled():
    security.set_permission("screen", enabled=True)
    decision = security.evaluate("take_screenshot", {})
    assert decision.needs_confirmation, "screenshots must always ask"
    assert decision.risk == Risk.SENSITIVE

    assert security.evaluate("list_windows", {}).needs_confirmation


def test_screenshot_saves_into_the_workspace(monkeypatch):
    security.set_permission("screen", enabled=True)

    class FakeImage:
        width, height = 1920, 1080

        def save(self, path):
            Path(path).write_bytes(b"\x89PNG fake")

    import sys
    import types
    fake_module = types.SimpleNamespace(grab=lambda: FakeImage())
    monkeypatch.setitem(sys.modules, "PIL", types.SimpleNamespace(ImageGrab=fake_module))
    monkeypatch.setitem(sys.modules, "PIL.ImageGrab", fake_module)

    result = pc_control.take_screenshot("demo")
    assert "screenshots/" in result and "1920x1080" in result
    saved = list((WS / "screenshots").glob("demo-*.png"))
    assert saved, "the screenshot should be in the workspace"


# ==========================================================================
# Phase 5 - communication. Nova must NEVER send by itself.
# ==========================================================================
def test_all_messaging_tools_are_sensitive_and_confirm():
    for name in ["whatsapp", "telegram", "messenger", "instagram", "email_draft"]:
        assert actions.REGISTRY[name]["risk"] == Risk.SENSITIVE, name
        assert security.evaluate(name, {}).needs_confirmation, name


def test_whatsapp_builds_a_prefilled_link(opened):
    result = comms.whatsapp("+880 17-1234 5678", "Hello from Nova")
    assert opened == ["https://wa.me/8801712345678?text=Hello%20from%20Nova"]
    assert "Press Send" in result, "the user must know they still press Send"


def test_whatsapp_rejects_a_bad_number(opened):
    with pytest.raises(comms.CommsError) as exc:
        comms.whatsapp("123", "hi")
    assert "country code" in str(exc.value)
    assert opened == [], "nothing should open for an invalid number"


def test_whatsapp_without_a_number_opens_the_picker(opened):
    comms.whatsapp("", "hello there")
    assert opened[0].startswith("https://wa.me/?text=")


def test_telegram_messenger_instagram_urls(opened):
    comms.telegram("novauser")
    comms.messenger("someone")
    comms.instagram("natgeo")
    comms.instagram()
    assert opened[0] == "https://t.me/novauser"
    assert opened[1] == "https://www.messenger.com/t/someone"
    assert opened[2] == "https://www.instagram.com/natgeo/"
    assert opened[3].endswith("/direct/inbox/")


def test_email_opens_a_draft_and_says_nothing_is_sent(opened):
    result = comms.email_draft("friend@example.com", "Hi", "How are you?")
    assert opened[0].startswith("mailto:friend@example.com?")
    assert "subject=Hi" in opened[0]
    assert "Nothing is sent" in result


@pytest.mark.parametrize("service,fragment", [
    ("youtube", "youtube.com/results"),
    ("spotify", "open.spotify.com/search"),
    ("ytmusic", "music.youtube.com/search"),
])
def test_play_music_picks_the_right_service(opened, service, fragment):
    comms.play_music("lofi beats", service)
    assert fragment in opened[0]
    assert "lofi%20beats" in opened[0]


def test_play_music_with_no_song_opens_the_app(opened):
    comms.play_music()
    assert opened == ["https://music.youtube.com"]


# ==========================================================================
# Phase 4 - web search
# ==========================================================================
SAMPLE_HTML = """
<div><a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fone">
First <b>result</b></a><a class="result__snippet">A snippet about one.</a></div>
<div><a class="result__a" href="https://example.org/two">Second result</a>
<a class="result__snippet">Another snippet.</a></div>
"""


def test_web_search_parses_results(monkeypatch):
    class FakeResponse:
        text = SAMPLE_HTML

        def raise_for_status(self):
            pass

    import httpx
    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse())

    out = web.search("example query")
    assert "First result" in out
    assert "https://example.com/one" in out, "the redirect wrapper must be unwrapped"
    assert "Second result" in out
    assert "A snippet about one." in out


def test_web_search_handles_network_failure(monkeypatch):
    import httpx

    def boom(*a, **k):
        raise httpx.ConnectError("no network")

    monkeypatch.setattr(httpx, "post", boom)
    with pytest.raises(web.WebError) as exc:
        web.search("anything")
    assert "internet" in str(exc.value).lower()


def test_web_search_needs_a_query():
    with pytest.raises(web.WebError):
        web.search("")


def test_web_search_returns_a_message_when_nothing_matches(monkeypatch):
    class Empty:
        text = "<html><body>no results here</body></html>"

        def raise_for_status(self):
            pass

    import httpx
    monkeypatch.setattr(httpx, "post", lambda *a, **k: Empty())
    assert "nothing usable" in web.search("zzzz")


# ==========================================================================
# Capability wiring
# ==========================================================================
def test_turning_off_messaging_blocks_every_messaging_tool():
    security.set_permission("messaging", enabled=False)
    for name in ["whatsapp", "telegram", "messenger", "instagram", "email_draft"]:
        assert security.evaluate(name, {}).denied, name


def test_turning_off_media_blocks_volume_and_music():
    security.set_permission("media", enabled=False)
    for name in ["volume_up", "media_play_pause", "play_music"]:
        assert security.evaluate(name, {}).denied, name


def test_new_capabilities_appear_in_the_permission_api(client):
    data = client.get("/api/permissions").json()
    keys = {c["key"] for c in data["capabilities"]}
    assert {"media", "screen", "messaging", "scheduler"} <= keys


def test_every_registered_tool_is_reachable_by_the_model():
    """Each tool must produce a valid schema for the model to call."""
    schemas = actions.tool_schemas()
    assert len(schemas) == len(actions.REGISTRY) >= 27
    for s in schemas:
        assert s["function"]["name"] in actions.REGISTRY
        assert s["function"]["description"]
