"""
Tests for Nova's actions (JARVIS mode) and the login system.

The safety rules are the important part here: if any of these fail, Nova
could touch files she should never touch.
"""

import os
import tempfile
from pathlib import Path

import pytest

WS = Path(tempfile.gettempdir()) / "nova_ws_test"
TMP_DB = Path(tempfile.gettempdir()) / "nova_actions_test.db"

os.environ["AI_OFFLINE_MOCK"] = "1"
os.environ["DB_PATH"] = str(TMP_DB)
os.environ["NOVA_WORKSPACE"] = str(WS)
os.environ["GIT_ROOT"] = str(WS)
os.environ["ACTION_LOG"] = str(WS / "actions.log")
os.environ["RATE_LIMIT_PER_MINUTE"] = "1000"
os.environ["ACTIONS_ENABLED"] = "true"

from fastapi.testclient import TestClient  # noqa: E402

from app.database.db import init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services import actions, agent  # noqa: E402


@pytest.fixture(autouse=True)
def clean_workspace():
    import shutil
    if WS.exists():
        shutil.rmtree(WS, ignore_errors=True)
    WS.mkdir(parents=True, exist_ok=True)
    yield


@pytest.fixture(scope="module")
def client():
    if TMP_DB.exists():
        TMP_DB.unlink()
    init_db()
    with TestClient(app) as c:
        yield c
    if TMP_DB.exists():
        TMP_DB.unlink()


# ==========================================================================
# SAFETY: the workspace sandbox
# ==========================================================================
@pytest.mark.parametrize("evil", [
    "../../../etc/passwd",
    "..\\..\\Windows\\System32",
    "/etc/passwd",
    "C:\\Windows\\System32",
    "../outside.txt",
    "subfolder/../../escape.txt",
])
def test_paths_outside_the_workspace_are_refused(evil):
    with pytest.raises(actions.ActionError) as exc:
        actions.safe_path(evil)
    assert "workspace" in str(exc.value).lower()


def test_paths_inside_the_workspace_are_allowed():
    p = actions.safe_path("notes/todo.txt")
    assert str(p).startswith(str(WS.resolve()))


def test_workspace_itself_cannot_be_deleted():
    with pytest.raises(actions.ActionError):
        actions.act_delete(".")


# ==========================================================================
# File actions
# ==========================================================================
def test_create_read_list_and_search():
    actions.act_create_folder("projects")
    actions.act_create_file("projects/hello.txt", "Hello from Nova")

    assert "hello.txt" in actions.act_list_files("projects")
    assert "Hello from Nova" in actions.act_read_file("projects/hello.txt")
    assert "hello.txt" in actions.act_search_files("hello")
    assert "Nothing matching" in actions.act_search_files("zzz-not-here")


def test_delete_is_recoverable_not_permanent():
    actions.act_create_file("bye.txt", "delete me")
    target = WS / "bye.txt"
    assert target.exists()

    result = actions.act_delete("bye.txt")
    assert not target.exists()
    # Either the OS Recycle Bin, or Nova's own trash folder.
    assert "Recycle Bin" in result or "nova_trash" in result

    if "nova_trash" in result:
        recovered = list((WS / ".nova_trash").rglob("bye.txt"))
        assert recovered, "the file should still be recoverable"
        assert recovered[0].read_text() == "delete me"


def test_move_and_rename():
    actions.act_create_file("a.txt", "x")
    actions.act_create_folder("archive")
    actions.act_move("a.txt", "archive/b.txt")
    assert (WS / "archive" / "b.txt").exists()
    assert not (WS / "a.txt").exists()


def test_move_refuses_to_overwrite():
    actions.act_create_file("one.txt", "1")
    actions.act_create_file("two.txt", "2")
    with pytest.raises(actions.ActionError):
        actions.act_move("one.txt", "two.txt")


def test_reading_a_missing_file_fails_clearly():
    with pytest.raises(actions.ActionError) as exc:
        actions.act_read_file("ghost.txt")
    assert "does not exist" in str(exc.value)


# ==========================================================================
# App / website actions
# ==========================================================================
def test_only_whitelisted_apps_can_be_opened():
    with pytest.raises(actions.ActionError) as exc:
        actions.act_open_app("format c:")
    assert "only open these apps" in str(exc.value)


def test_dangerous_url_schemes_are_refused():
    for bad in ["file:///etc/passwd", "javascript:alert(1)", "data:text/html,x"]:
        with pytest.raises(actions.ActionError):
            actions.act_open_website(site=bad)


def test_site_shortcuts_resolve(monkeypatch):
    opened = []
    monkeypatch.setattr(actions.webbrowser, "open", lambda u: opened.append(u))
    actions.act_open_website(site="youtube")
    actions.act_open_website(site="example.org")
    assert opened[0] == "https://www.youtube.com"
    assert opened[1] == "https://example.org"


# ==========================================================================
# Git guard rails
# ==========================================================================
def test_git_rejects_commands_outside_the_allow_list():
    with pytest.raises(actions.ActionError) as exc:
        actions.act_git("reset --hard")
    assert "only run these git commands" in str(exc.value)


def test_git_needs_a_real_repository():
    with pytest.raises(actions.ActionError) as exc:
        actions.act_git("status")
    assert "not a git repository" in str(exc.value)


def test_commit_without_message_is_refused():
    (WS / ".git").mkdir(parents=True, exist_ok=True)
    with pytest.raises(actions.ActionError) as exc:
        actions.act_git("commit", message="   ")
    assert "needs a message" in str(exc.value)


# ==========================================================================
# Confirmation flow
# ==========================================================================
def test_destructive_actions_need_confirmation():
    assert actions.needs_confirmation("delete_path", {"path": "x"}) is True
    assert actions.needs_confirmation("move_path", {"source": "a", "destination": "b"}) is True
    assert actions.needs_confirmation("git", {"command": "push"}) is True
    # Read-only things run straight away.
    assert actions.needs_confirmation("list_files", {}) is False
    assert actions.needs_confirmation("open_website", {"site": "youtube"}) is False
    assert actions.needs_confirmation("git", {"command": "status"}) is False


def test_confirm_endpoint_runs_the_parked_action(client):
    actions.act_create_file("confirm-me.txt", "data")
    token = agent.park_action("delete_path", {"path": "confirm-me.txt"}, 0)

    res = client.post("/api/actions/confirm", json={"token": token})
    assert res.status_code == 200, res.text
    assert not (WS / "confirm-me.txt").exists()

    # A token can only be used once.
    again = client.post("/api/actions/confirm", json={"token": token})
    assert again.status_code == 400


def test_cancel_endpoint_does_not_run_the_action(client):
    actions.act_create_file("keep-me.txt", "data")
    token = agent.park_action("delete_path", {"path": "keep-me.txt"}, 0)

    assert client.post("/api/actions/cancel", json={"token": token}).json()["ok"] is True
    assert (WS / "keep-me.txt").exists(), "cancelled action must not run"
    assert client.post("/api/actions/confirm", json={"token": token}).status_code == 400


def test_unknown_token_is_rejected(client):
    res = client.post("/api/actions/confirm", json={"token": "not-a-real-token"})
    assert res.status_code == 400


# ==========================================================================
# Registry / API
# ==========================================================================
def test_every_action_has_a_valid_tool_schema():
    schemas = actions.tool_schemas()
    assert len(schemas) == len(actions.REGISTRY)
    for s in schemas:
        fn = s["function"]
        assert fn["name"] in actions.REGISTRY
        assert fn["description"]
        assert s["type"] == "function"
        for required in fn["parameters"]["required"]:
            assert required in fn["parameters"]["properties"]


def test_unknown_action_is_refused():
    with pytest.raises(actions.ActionError):
        actions.execute("rm_rf_everything", {})


def test_actions_are_logged(client):
    actions.execute("current_time", {})
    log = Path(os.environ["ACTION_LOG"])
    assert log.exists()
    assert "current_time" in log.read_text()


def test_actions_endpoint_lists_abilities(client):
    data = client.get("/api/actions").json()
    assert data["enabled"] is True
    assert "delete_path" in [a["name"] for a in data["abilities"]]
    assert "youtube" in data["websites"]


# ==========================================================================
# Login
# ==========================================================================
def test_no_password_means_open_access(client):
    from app.services import auth
    assert auth.auth_required() is False
    assert client.get("/api/conversations").status_code == 200


def test_password_protects_everything(monkeypatch):
    from app.config import settings
    from app.services import auth

    monkeypatch.setattr(settings, "AUTH_PASSWORD", "secret123")
    with TestClient(app) as c:
        # Locked out without a cookie.
        assert c.get("/api/conversations").status_code == 401
        assert c.post("/api/chat", json={"message": "hi"}).status_code == 401
        # The page redirects to the login screen.
        assert c.get("/", follow_redirects=False).status_code == 302

        # Wrong password.
        assert c.post("/api/login", json={"password": "wrong"}).status_code == 401

        # Right password unlocks it.
        assert c.post("/api/login", json={"password": "secret123"}).status_code == 200
        assert c.get("/api/conversations").status_code == 200

        c.post("/api/logout")
        assert c.get("/api/conversations").status_code == 401


def test_session_tokens_cannot_be_forged(monkeypatch):
    from app.config import settings
    from app.services import auth

    monkeypatch.setattr(settings, "AUTH_PASSWORD", "secret123")
    good = auth.make_token()
    assert auth.token_is_valid(good) is True

    body, signature = good.rsplit(".", 1)
    assert auth.token_is_valid(f"{body}.{'0' * len(signature)}") is False
    assert auth.token_is_valid("garbage") is False
    assert auth.token_is_valid("") is False
