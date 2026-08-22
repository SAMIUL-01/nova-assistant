"""
Backend tests. Run from the project root with:

    venv\\Scripts\\activate
    pytest -v

These tests use AI_OFFLINE_MOCK so they never call OpenRouter and never
need an API key. They also use a throwaway database file.
"""

import os
import tempfile
from pathlib import Path

import pytest

# Configure the app BEFORE importing it.
TMP_DB = Path(tempfile.gettempdir()) / "chat_test.db"
os.environ["AI_OFFLINE_MOCK"] = "1"
os.environ["DB_PATH"] = str(TMP_DB)
os.environ["MAX_MESSAGE_CHARS"] = "500"
os.environ["RATE_LIMIT_PER_MINUTE"] = "1000"

from fastapi.testclient import TestClient  # noqa: E402

from app.database.db import init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services.titles import make_title  # noqa: E402


@pytest.fixture(autouse=True)
def small_message_limit(monkeypatch):
    """Settings are read at call time, so patch the object -- environment
    variables only win for whichever test module imports the app first."""
    from app.config import settings
    monkeypatch.setattr(settings, "MAX_MESSAGE_CHARS", 500)
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


def test_health(client):
    data = client.get("/api/health").json()
    assert data["status"] == "ok"
    assert data["offline_mock"] is True


def test_homepage_serves_html(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "<html" in res.text.lower()


def test_create_and_list_conversation(client):
    created = client.post("/api/conversations", json={"title": "Test Chat"})
    assert created.status_code == 201
    cid = created.json()["id"]

    listed = client.get("/api/conversations").json()
    assert any(c["id"] == cid for c in listed)


def test_chat_creates_conversation_and_saves_messages(client):
    res = client.post("/api/chat", json={"message": "How does Java inheritance work?"})
    assert res.status_code == 200
    body = res.json()
    cid = body["conversation_id"]
    assert body["message"]
    assert body["title"] == "Java Inheritance Work"

    detail = client.get(f"/api/conversations/{cid}").json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]


def test_conversation_memory_grows(client):
    first = client.post("/api/chat", json={"message": "My name is Alex."}).json()
    cid = first["conversation_id"]
    client.post("/api/chat", json={"conversation_id": cid, "message": "What is my name?"})

    detail = client.get(f"/api/conversations/{cid}").json()
    # 2 user + 2 assistant messages
    assert len(detail["messages"]) == 4


def test_streaming_endpoint(client):
    with client.stream(
        "POST", "/api/chat/stream", json={"message": "Stream test please"}
    ) as res:
        assert res.status_code == 200
        text = "".join(res.iter_text())
    assert "event: start" in text
    assert "event: token" in text
    assert "event: done" in text


def test_empty_message_rejected(client):
    res = client.post("/api/chat", json={"message": "   "})
    assert res.status_code == 400
    assert "empty" in res.json()["detail"].lower()


def test_too_long_message_rejected(client):
    res = client.post("/api/chat", json={"message": "x" * 501})
    assert res.status_code == 400
    assert "too long" in res.json()["detail"].lower()


def test_unknown_conversation_returns_404(client):
    assert client.get("/api/conversations/999999").status_code == 404
    res = client.post("/api/chat", json={"conversation_id": 999999, "message": "hi"})
    assert res.status_code == 404


def test_delete_conversation_removes_messages(client):
    cid = client.post("/api/chat", json={"message": "delete me"}).json()["conversation_id"]
    assert client.delete(f"/api/conversations/{cid}").json()["ok"] is True
    assert client.get(f"/api/conversations/{cid}").status_code == 404
    assert client.delete(f"/api/conversations/{cid}").status_code == 404


@pytest.mark.parametrize(
    "message,expected",
    [
        ("How does Java inheritance work?", "Java Inheritance Work"),
        ("what is SQL?", "SQL"),
        ("", "New Chat"),
        ("!!! ???", "New Chat"),
    ],
)
def test_title_generation(message, expected):
    assert make_title(message) == expected
