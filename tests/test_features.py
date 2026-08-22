"""
Tests for long-term memory and file uploads.

Run with:  pytest -v

Uses offline mock mode, so no API key and no internet are needed.
"""

import io
import os
import tempfile
from pathlib import Path

import pytest

TMP_DB = Path(tempfile.gettempdir()) / "chat_features_test.db"
TMP_UPLOADS = Path(tempfile.gettempdir()) / "chat_test_uploads"
os.environ["AI_OFFLINE_MOCK"] = "1"
os.environ["DB_PATH"] = str(TMP_DB)
os.environ["UPLOAD_DIR"] = str(TMP_UPLOADS)
os.environ["RATE_LIMIT_PER_MINUTE"] = "1000"

from fastapi.testclient import TestClient  # noqa: E402

from app.database.db import init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services import documents, memory  # noqa: E402


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
    """Give this module its own writable upload folder."""
    from app.config import settings
    monkeypatch.setattr(settings, "UPLOAD_DIR",
                        tmp_path_factory.mktemp("uploads"))
    yield


@pytest.fixture(autouse=True)
def clean_memory(client):
    client.delete("/api/memory")
    yield


# ==========================================================================
# Memory: rule-based extraction
# ==========================================================================
@pytest.mark.parametrize(
    "message,expected_fragment",
    [
        ("Hi, my name is Sam", "name is Sam"),
        ("I am a computer science student", "is a computer science student"),
        ("I live in Dhaka, Bangladesh", "lives in Dhaka"),
        ("I'm learning FastAPI and React", "learning FastAPI and React"),
        ("Please remember that I hate long answers", "hate long answers"),
        ("my favourite language is Python", "favourite language is Python"),
        ("I work at Acme Corp", "works at Acme Corp"),
    ],
)
def test_rules_extract_facts(message, expected_fragment):
    facts = memory.extract_with_rules(message)
    assert any(expected_fragment.lower() in f.lower() for f in facts), facts


@pytest.mark.parametrize(
    "message",
    [
        "What is thermodynamics?",
        "Write me a python function",
        "hello",
        "",
    ],
)
def test_rules_ignore_ordinary_messages(message):
    assert memory.extract_with_rules(message) == []


def test_ai_fact_parser_tolerates_messy_output():
    assert memory._parse_json_facts('["The user is a student."]') == [
        "The user is a student."
    ]
    # Code fences and chatter around the JSON.
    messy = 'Sure!\n```json\n["The user likes tea."]\n```'
    assert memory._parse_json_facts(messy) == ["The user likes tea."]
    # Empty and invalid cases.
    assert memory._parse_json_facts("[]") == []
    assert memory._parse_json_facts("no json here") == []
    assert memory._parse_json_facts("") == []


def test_duplicate_facts_are_not_stored_twice():
    memory.remember(["The user's name is Sam."])
    memory.remember(["The user's name is Sam."])       # exact repeat
    memory.remember(["the users name is Sam"])          # near duplicate
    facts = memory.__dict__  # keep linters quiet
    from app.database import db

    contents = [f["content"] for f in db.list_memories()]
    assert len([c for c in contents if "Sam" in c]) == 1


# ==========================================================================
# Memory: API + injection into the prompt
# ==========================================================================
def test_memory_crud(client):
    empty = client.get("/api/memory").json()
    assert empty["count"] == 0

    created = client.post("/api/memory", json={"content": "The user prefers short answers."})
    assert created.status_code == 201
    memory_id = created.json()["id"]

    listed = client.get("/api/memory").json()
    assert listed["count"] == 1
    assert listed["facts"][0]["source"] == "manual"

    # Duplicates are rejected.
    assert client.post(
        "/api/memory", json={"content": "The user prefers short answers."}
    ).status_code == 409

    # Too short.
    assert client.post("/api/memory", json={"content": "x"}).status_code == 400

    assert client.delete(f"/api/memory/{memory_id}").json()["ok"] is True
    assert client.delete(f"/api/memory/{memory_id}").status_code == 404
    assert client.get("/api/memory").json()["count"] == 0


def test_memory_is_learned_from_chat_and_reused(client):
    """The whole point: say it once, and it is known in a brand new chat."""
    first = client.post("/api/chat", json={"message": "Hello, my name is Sam."})
    assert first.status_code == 200

    facts = [f["content"] for f in client.get("/api/memory").json()["facts"]]
    assert any("Sam" in f for f in facts), facts

    # A completely separate conversation now receives the memory block.
    second = client.post("/api/chat", json={"message": "What should I build today?"})
    assert "long-term memory" in second.json()["message"]


def test_chat_works_when_memory_is_empty(client):
    reply = client.post("/api/chat", json={"message": "Just a normal question"}).json()
    assert "Context received" not in reply["message"]


def test_clear_all_memories(client):
    client.post("/api/memory", json={"content": "Fact one about the user."})
    client.post("/api/memory", json={"content": "Fact two about the user."})
    result = client.delete("/api/memory").json()
    assert result["ok"] is True
    assert client.get("/api/memory").json()["count"] == 0


# ==========================================================================
# Documents: chunking and retrieval
# ==========================================================================
def test_chunking_splits_and_overlaps():
    text = "\n\n".join(f"Paragraph number {i} with some filler words." for i in range(80))
    chunks = documents.chunk_text(text, size=400, overlap=50)
    assert len(chunks) > 1
    assert all(len(c) <= 500 for c in chunks)
    assert "".join(chunks).count("Paragraph number 1 ") >= 1


def test_retrieval_ranks_the_relevant_chunk_first():
    chunks = [
        {"content": "Bananas are yellow fruit.", "filename": "f", "idx": 0, "document_id": 1},
        {"content": "The mitochondrion is the powerhouse of the cell.",
         "filename": "f", "idx": 1, "document_id": 1},
        {"content": "Python uses indentation for blocks.",
         "filename": "f", "idx": 2, "document_id": 1},
    ]
    ranked = documents._score_chunks("tell me about the mitochondrion", chunks)
    assert ranked, "expected at least one match"
    assert "mitochondrion" in ranked[0][1]["content"]


def test_upload_txt_then_ask_about_it(client):
    conversation_id = client.post("/api/chat", json={"message": "start"}).json()[
        "conversation_id"
    ]

    content = (
        "Project Zeta specification.\n\n"
        "The deployment deadline is 14 March 2027.\n\n"
        "The lead engineer is Fatima Rahman.\n\n"
    ) + "\n\n".join(f"Filler paragraph {i}." for i in range(50))

    res = client.post(
        "/api/upload",
        files={"file": ("spec.txt", io.BytesIO(content.encode()), "text/plain")},
        data={"conversation_id": str(conversation_id)},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["filename"] == "spec.txt"
    assert body["chunk_count"] >= 1

    listed = client.get(f"/api/conversations/{conversation_id}/documents").json()
    assert len(listed) == 1

    # Asking about the document should send excerpts to the model.
    reply = client.post(
        "/api/chat",
        json={"conversation_id": conversation_id,
              "message": "Who is the lead engineer for Project Zeta?"},
    ).json()
    assert "document excerpts" in reply["message"]

    # And the retrieved excerpt should be the relevant one.
    from app.services.documents import build_context

    context = build_context(conversation_id, "Who is the lead engineer?")
    assert "Fatima Rahman" in context

    assert client.delete(f"/api/documents/{body['id']}").json()["ok"] is True
    assert client.get(f"/api/conversations/{conversation_id}/documents").json() == []


def test_upload_pdf(client):
    """Real PDF, generated on the fly, must have its text extracted."""
    reportlab = pytest.importorskip("reportlab")
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(100, 750, "Invoice number 4815 for Hydra Industries.")
    pdf.drawString(100, 730, "Total due is 2360 euros.")
    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    res = client.post(
        "/api/upload",
        files={"file": ("invoice.pdf", buffer, "application/pdf")},
    )
    assert res.status_code == 201, res.text
    assert res.json()["text_chars"] > 20

    from app.services.documents import build_context

    context = build_context(None, "what is the invoice number?")
    assert "4815" in context


def test_upload_rejects_images_with_a_helpful_message(client):
    res = client.post(
        "/api/upload",
        files={"file": ("photo.png", io.BytesIO(b"\x89PNG fake"), "image/png")},
    )
    assert res.status_code == 400
    assert "vision model" in res.json()["detail"]


def test_upload_rejects_unsupported_and_empty_files(client):
    res = client.post(
        "/api/upload", files={"file": ("thing.xyz", io.BytesIO(b"data"), "application/x")}
    )
    assert res.status_code == 400
    assert "Unsupported file type" in res.json()["detail"]

    res = client.post(
        "/api/upload", files={"file": ("empty.txt", io.BytesIO(b""), "text/plain")}
    )
    assert res.status_code == 400
    assert "empty" in res.json()["detail"].lower()


def test_upload_too_large_is_rejected(client):
    from app.config import settings

    oversized = b"a" * (settings.MAX_UPLOAD_MB * 1024 * 1024 + 10)
    res = client.post(
        "/api/upload", files={"file": ("big.txt", io.BytesIO(oversized), "text/plain")}
    )
    assert res.status_code == 400
    assert "limit is" in res.json()["detail"]


def test_upload_to_unknown_conversation_is_404(client):
    res = client.post(
        "/api/upload",
        files={"file": ("a.txt", io.BytesIO(b"hello world"), "text/plain")},
        data={"conversation_id": "999999"},
    )
    assert res.status_code == 404


def test_deleting_a_conversation_removes_its_documents(client):
    cid = client.post("/api/chat", json={"message": "doc owner chat"}).json()[
        "conversation_id"
    ]
    client.post(
        "/api/upload",
        files={"file": ("temp.txt", io.BytesIO(b"some content here"), "text/plain")},
        data={"conversation_id": str(cid)},
    )
    from app.database import db

    before = [c["filename"] for c in db.get_chunks_for_conversation(cid)]
    assert "temp.txt" in before

    client.delete(f"/api/conversations/{cid}")

    # The conversation's own file is gone. (Files uploaded with no
    # conversation_id are global reference docs and stay available.)
    after = [c["filename"] for c in db.get_chunks_for_conversation(cid)]
    assert "temp.txt" not in after
