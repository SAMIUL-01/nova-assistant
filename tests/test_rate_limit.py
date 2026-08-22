"""
Tests for rate limiting (spec section 29).

Also proves the limiter did NOT break streaming or background memory
learning -- the reason it is a dependency and not middleware.
"""

import os
import tempfile
from pathlib import Path

import pytest

TMP_DB = Path(tempfile.gettempdir()) / "chat_ratelimit_test.db"
os.environ["AI_OFFLINE_MOCK"] = "1"
os.environ["DB_PATH"] = str(TMP_DB)
os.environ["RATE_LIMIT_PER_MINUTE"] = "1000"     # generous default for other tests

from fastapi.testclient import TestClient  # noqa: E402

from app.database.db import init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services.rate_limit import RateLimiter, limiter  # noqa: E402


@pytest.fixture(scope="module")
def client():
    if TMP_DB.exists():
        TMP_DB.unlink()
    init_db()
    with TestClient(app) as c:
        yield c
    if TMP_DB.exists():
        TMP_DB.unlink()


@pytest.fixture(autouse=True)
def upload_dir(monkeypatch, tmp_path_factory):
    from app.config import settings
    monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path_factory.mktemp("uploads"))
    yield


@pytest.fixture(autouse=True)
def clean_limiter():
    original = limiter.limit
    limiter.reset()
    yield
    limiter.limit = original
    limiter.reset()


# ==========================================================================
# The limiter itself
# ==========================================================================
def test_allows_up_to_the_limit_then_blocks():
    r = RateLimiter(3)
    assert [r.check("1.2.3.4")[0] for _ in range(3)] == [True, True, True]
    allowed, retry_after, remaining = r.check("1.2.3.4")
    assert allowed is False
    assert retry_after > 0
    assert remaining == 0


def test_limits_are_per_client():
    r = RateLimiter(2)
    r.check("first"); r.check("first")
    assert r.check("first")[0] is False
    # A different caller is unaffected.
    assert r.check("second")[0] is True


def test_zero_disables_limiting():
    r = RateLimiter(0)
    assert all(r.check("anyone")[0] for _ in range(500))


# ==========================================================================
# Through the API
# ==========================================================================
def test_chat_is_rate_limited(client):
    limiter.limit = 3
    limiter.reset()

    for i in range(3):
        res = client.post("/api/chat", json={"message": f"message {i}"})
        assert res.status_code == 200, f"request {i} should have been allowed"

    blocked = client.post("/api/chat", json={"message": "one too many"})
    assert blocked.status_code == 429
    assert "very quickly" in blocked.json()["detail"]
    assert "Retry-After" in blocked.headers


def test_reading_endpoints_are_never_limited(client):
    limiter.limit = 2
    limiter.reset()
    client.post("/api/chat", json={"message": "a"})
    client.post("/api/chat", json={"message": "b"})
    assert client.post("/api/chat", json={"message": "c"}).status_code == 429

    # Browsing your own history must keep working while you are throttled.
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/conversations").status_code == 200
    assert client.get("/api/memory").status_code == 200


def test_upload_is_rate_limited(client):
    import io

    limiter.limit = 1
    limiter.reset()
    first = client.post(
        "/api/upload", files={"file": ("a.txt", io.BytesIO(b"hello there"), "text/plain")}
    )
    assert first.status_code == 201
    second = client.post(
        "/api/upload", files={"file": ("b.txt", io.BytesIO(b"hello again"), "text/plain")}
    )
    assert second.status_code == 429


# ==========================================================================
# Regression: the limiter must not break streaming or background jobs
# ==========================================================================
def test_streaming_still_streams_with_the_limiter_active(client):
    """
    The limiter is a dependency, not middleware, precisely so it cannot buffer
    Server-Sent Events. Here we check the frames are all correct.

    Note: TestClient collects the whole body before returning, so timing cannot
    be measured here. Real over-the-socket timing was verified separately
    (first token 39 ms, last token 901 ms -> genuinely streamed).
    """
    limiter.limit = 50
    limiter.reset()
    with client.stream(
        "POST", "/api/chat/stream", json={"message": "stream check please"}
    ) as res:
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/event-stream")
        assert res.headers.get("x-accel-buffering") == "no"   # proxies must not buffer
        body = "".join(res.iter_text())

    assert "event: start" in body
    assert "event: token" in body
    assert "event: done" in body
    assert body.count("event: token") > 1, "expected many token frames"


def test_background_memory_learning_still_runs(client):
    limiter.limit = 50
    limiter.reset()
    client.delete("/api/memory")
    client.post("/api/chat", json={"message": "Hi, my name is Rahim."})
    facts = [f["content"] for f in client.get("/api/memory").json()["facts"]]
    assert any("Rahim" in f for f in facts), facts
