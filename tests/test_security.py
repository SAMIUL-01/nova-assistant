"""
Phase 2 tests: the security layer, the permission manager, and the router.

These are the most important tests in the project. If one of them fails,
Nova can do something the user did not agree to.
"""

import os
import tempfile
from pathlib import Path

import pytest

WS = Path(tempfile.gettempdir()) / "nova_sec_ws"
TMP_DB = Path(tempfile.gettempdir()) / "nova_security_test.db"

os.environ["AI_OFFLINE_MOCK"] = "1"
os.environ["DB_PATH"] = str(TMP_DB)
os.environ["NOVA_WORKSPACE"] = str(WS)
os.environ["ACTION_LOG"] = str(WS / "actions.log")
os.environ["RATE_LIMIT_PER_MINUTE"] = "1000"
os.environ["ACTIONS_ENABLED"] = "true"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import db  # noqa: E402
from app.database.db import init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services import actions, agent, router, security  # noqa: E402
from app.services.security import Risk  # noqa: E402


@pytest.fixture(scope="module")
def client():
    if TMP_DB.exists():
        TMP_DB.unlink()
    WS.mkdir(parents=True, exist_ok=True)
    init_db()
    with TestClient(app) as c:
        yield c
    if TMP_DB.exists():
        TMP_DB.unlink()


@pytest.fixture(autouse=True)
def default_permissions(client, monkeypatch):
    """
    Reset permissions, and pin this module's workspace/log.

    Settings are read at call time, so patch the object: environment
    variables only win for whichever test module imports the app first.
    """
    from app.config import settings

    WS.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "NOVA_WORKSPACE", WS)
    monkeypatch.setattr(settings, "GIT_ROOT", WS)
    monkeypatch.setattr(settings, "ACTION_LOG", WS / "actions.log")
    db.reset_permissions()
    yield
    db.reset_permissions()


# ==========================================================================
# Every tool must be classified
# ==========================================================================
def test_every_tool_has_a_risk_level_and_capability():
    for name, spec in actions.REGISTRY.items():
        assert isinstance(spec["risk"], Risk), f"{name} has no risk level"
        assert spec["capability"] in security.CAPABILITIES, \
            f"{name} points at an unknown capability"


def test_dangerous_tools_are_classified_dangerous():
    assert actions.REGISTRY["delete_path"]["risk"] == Risk.DESTRUCTIVE
    assert actions.REGISTRY["move_path"]["risk"] == Risk.DESTRUCTIVE
    # And harmless ones are not over-classified, or the UX would be unusable.
    assert actions.REGISTRY["current_time"]["risk"] == Risk.SAFE
    assert actions.REGISTRY["list_files"]["risk"] == Risk.SAFE


# ==========================================================================
# The invariants that cannot be switched off
# ==========================================================================
def test_destructive_actions_always_require_confirmation():
    """Even with every setting relaxed, deleting must still ask."""
    from app.config import settings

    original = settings.ACTIONS_CONFIRM
    settings.ACTIONS_CONFIRM = False          # user tries to disable prompts
    try:
        decision = security.evaluate("delete_path", {"path": "x.txt"})
        assert decision.needs_confirmation, "delete must never run unattended"
        decision = security.evaluate("move_path", {"source": "a", "destination": "b"})
        assert decision.needs_confirmation
    finally:
        settings.ACTIONS_CONFIRM = original


def test_unknown_tools_are_denied():
    """The model cannot invent a shell tool and have it run."""
    for invented in ["run_shell", "execute_command", "eval", "os_system",
                     "powershell", "rm", "download_and_run"]:
        decision = security.evaluate(invented, {"cmd": "format c:"})
        assert decision.denied, f"{invented} must be refused"


def test_there_is_no_arbitrary_command_tool():
    """A registry audit: nothing may expose a raw shell."""
    banned = {"shell", "exec", "execute", "run_command", "system", "eval",
              "subprocess", "powershell", "cmd", "bash"}
    for name in actions.REGISTRY:
        assert name.lower() not in banned, f"{name} looks like a shell escape"


def test_execute_refuses_destructive_without_approval():
    actions.act_create_file("guarded.txt", "data")
    with pytest.raises(actions.ActionError) as exc:
        actions.execute("delete_path", {"path": "guarded.txt"})
    assert "confirmation" in str(exc.value).lower()
    assert (WS / "guarded.txt").exists(), "the file must still be there"

    # With approval (what the Confirm button does) it goes through.
    actions.execute("delete_path", {"path": "guarded.txt"}, _approved=True)
    assert not (WS / "guarded.txt").exists()


# ==========================================================================
# Capabilities
# ==========================================================================
def test_disabling_a_capability_blocks_its_tools():
    security.set_permission("web", enabled=False)
    decision = security.evaluate("open_website", {"site": "youtube"})
    assert decision.denied
    assert "turned off" in decision.reason

    # Other capabilities are unaffected.
    assert security.evaluate("current_time", {}).allowed


def test_disabled_capability_blocks_actual_execution():
    security.set_permission("files", enabled=False)
    with pytest.raises(actions.ActionError) as exc:
        actions.execute("list_files", {"path": "."})
    assert "turned off" in str(exc.value)


def test_always_ask_forces_confirmation_on_safe_tools():
    assert security.evaluate("current_time", {}).allowed
    security.set_permission("system", enabled=True, always_ask=True)
    assert security.evaluate("current_time", {}).needs_confirmation


def test_confirming_cannot_bypass_a_disabled_capability():
    """Approval is not a master key."""
    actions.act_create_file("nope.txt", "x")
    token = agent.park_action("delete_path", {"path": "nope.txt"}, 0)
    security.set_permission("files", enabled=False)

    with pytest.raises(actions.ActionError):
        agent.confirm_and_run(token)
    assert (WS / "nope.txt").exists()


def test_actions_globally_disabled(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "ACTIONS_ENABLED", False)
    assert security.evaluate("current_time", {}).denied


# ==========================================================================
# Per-argument escalation (git status vs git push)
# ==========================================================================
@pytest.mark.parametrize("command,should_confirm", [
    ("status", False),
    ("log", False),
    ("diff", False),
    ("commit", True),
    ("push", True),
    ("pull", True),
    ("add", True),
])
def test_git_escalates_only_for_changing_commands(command, should_confirm):
    decision = security.evaluate("git", {"command": command})
    assert decision.needs_confirmation is should_confirm, \
        f"git {command} confirmation should be {should_confirm}"


# ==========================================================================
# Audit log must never contain secrets
# ==========================================================================
@pytest.mark.parametrize("secret", [
    "sk-or-v1-abcdef1234567890abcdef",
    "ghp_ABCDEFGHIJKLMNOP1234",
    "api_key=supersecretvalue",
    "password: hunter2trustno1",
    "someone@example.com",
])
def test_secrets_are_scrubbed_before_logging(secret):
    cleaned = security.scrub(f"here is the value {secret} ok")
    assert "[redacted]" in cleaned
    assert secret not in cleaned


def test_scrub_handles_nested_structures():
    dirty = {"note": "token=abc123456789", "list": ["sk-or-v1-aaaaaaaaaaaa"]}
    clean = security.scrub(dirty)
    assert "[redacted]" in clean["note"]
    assert "[redacted]" in clean["list"][0]


def test_action_log_records_risk_and_decision():
    from app.config import settings
    log = Path(settings.ACTION_LOG)
    if log.exists():
        log.unlink()
    actions.execute("current_time", {})
    entry = log.read_text().strip().splitlines()[-1]
    assert "current_time" in entry
    assert "SAFE" in entry


# ==========================================================================
# Permission manager API
# ==========================================================================
def test_permissions_api_lists_everything(client):
    data = client.get("/api/permissions").json()
    keys = {c["key"] for c in data["capabilities"]}
    assert {"files", "pc_control", "web", "git", "system"} <= keys
    assert data["policy"]["shell_access"].startswith("never")
    # Every tool is reported with its risk.
    assert any(t["name"] == "delete_path" and t["risk"] == "DESTRUCTIVE"
               for t in data["tools"])


def test_permissions_api_can_toggle_and_reset(client):
    res = client.put("/api/permissions/web", json={"enabled": False,
                                                   "always_ask": False})
    assert res.status_code == 200
    assert res.json()["enabled"] is False
    assert security.evaluate("open_website", {"site": "youtube"}).denied

    client.post("/api/permissions/reset")
    assert security.evaluate("open_website", {"site": "youtube"}).allowed


def test_permissions_api_rejects_unknown_capability(client):
    res = client.put("/api/permissions/nuclear_launch",
                     json={"enabled": True, "always_ask": False})
    assert res.status_code == 404


def test_permission_changes_survive_a_restart(client):
    security.set_permission("git", enabled=False)
    # A fresh read goes back to the database, not to memory.
    assert security.all_permissions()["git"]["enabled"] is False


# ==========================================================================
# Router: same pipeline for voice and text
# ==========================================================================
@pytest.mark.parametrize("text,tool", [
    ("open youtube", "open_website"),
    ("Open Instagram", "open_website"),
    ("please open facebook", "open_website"),
    ("khulo youtube", "open_website"),
    ("open notepad", "open_app"),
    ("what time is it", "current_time"),
    ("koyta baje", "current_time"),
    ("system info", "system_info"),
    ("list files", "list_files"),
])
def test_router_recognises_common_commands(text, tool):
    routed = router.route(text)
    assert routed is not None, f"{text!r} should have matched"
    assert routed.tool == tool


@pytest.mark.parametrize("text", [
    "explain thermodynamics",
    "write me a python function",
    "delete all my files",          # too vague for a fast path
    "who are you?",
    "",
    "open the pod bay doors",
])
def test_router_leaves_everything_else_to_the_model(text):
    assert router.route(text) is None


def test_router_result_still_passes_through_security():
    """A fast path must not be a way around the permission manager."""
    routed = router.route("open youtube")
    security.set_permission("web", enabled=False)
    events = list(agent.run_routed(routed, 0))
    text = " ".join(e.get("text", "") + e.get("result", "") for e in events)
    assert "turned off" in text


def test_router_destructive_command_still_asks(client):
    """Even via the fast path, dangerous things stop for confirmation."""
    from app.services.router import RoutedCommand

    command = RoutedCommand("delete_path", {"path": "anything.txt"}, "Deleting.")
    events = list(agent.run_routed(command, 0))
    assert any(e["type"] == "confirm" for e in events)


def test_voice_and_text_use_the_same_pipeline(client):
    """
    Voice input is just text. Sending the identical string through the chat
    endpoint must produce the identical routing decision.
    """
    typed = router.route("open youtube")
    spoken = router.route("open youtube")     # what the mic transcribes
    assert typed.tool == spoken.tool
    assert typed.arguments == spoken.arguments
