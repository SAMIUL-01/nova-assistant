"""
Long-term memory.

Facts learned here are injected into EVERY conversation, so the assistant
knows who you are without being told again.

Two extraction paths, on purpose:

1. Rules  - regex patterns ("my name is ...", "remember that ..."). Instant,
            free, works offline, and never fails.
2. AI     - asks the model to pull out durable facts as JSON. Catches things
            the rules miss. Skipped in offline mock mode.

The user can view, add, and delete every stored fact from the UI, so nothing
is remembered secretly.
"""

import json
import logging
import re
from typing import List

from app.config import settings
from app.database import db

logger = logging.getLogger(__name__)

MAX_FACT_CHARS = 200

# --------------------------------------------------------------------------
# Rule-based extraction
# --------------------------------------------------------------------------
# Each pattern maps a phrase the user typed to a fact worth storing.
RULES = [
    (r"\bremember\s+(?:that\s+|this[:,]?\s*|)(.{4,200})", "{0}"),
    (r"\bmy name is\s+([A-Za-z][\w'\-]{1,30})", "The user's name is {0}."),
    (r"\bcall me\s+([A-Za-z][\w'\-]{1,30})", "The user prefers to be called {0}."),
    (r"\bi(?:'m| am)\s+(?:a|an)\s+([A-Za-z][\w\s\-/]{2,45})", "The user is a {0}."),
    (r"\bi(?:'m| am)\s+from\s+([A-Za-z][\w\s,\-]{2,45})", "The user is from {0}."),
    (r"\bi live in\s+([A-Za-z][\w\s,\-]{2,45})", "The user lives in {0}."),
    (r"\bi(?:'m| am)\s+studying\s+([A-Za-z][\w\s,+#\-\.]{2,45})",
     "The user is studying {0}."),
    (r"\bi(?:'m| am)\s+learning\s+([A-Za-z][\w\s,+#\-\.]{2,45})",
     "The user is learning {0}."),
    (r"\bi work (?:at|for)\s+([A-Za-z][\w\s&,\-\.]{2,45})", "The user works at {0}."),
    (r"\bi study at\s+([A-Za-z][\w\s&,\-\.]{2,45})", "The user studies at {0}."),
    (r"\bmy (?:favou?rite)\s+([\w\s]{2,25})\s+is\s+([\w\s+#\-\.]{2,35})",
     "The user's favourite {0} is {1}."),
    (r"\bi prefer\s+([\w\s,+#\-\.]{3,45})", "The user prefers {0}."),
    (r"\bi(?:'m| am)\s+working on\s+([\w\s,+#\-\.]{3,45})",
     "The user is working on {0}."),
    (r"\bmy (?:goal|dream) is\s+(.{4,120})", "The user's goal is {0}."),
]

# Things that should never become a "fact".
JUNK = re.compile(
    r"^(?:the user (?:is|prefers|works at|lives in) )?(?:it|that|this|not sure|nothing|"
    r"ok|okay|yes|no|hi|hello|test)\b\.?$",
    re.IGNORECASE,
)


def _tidy(text: str) -> str:
    text = re.sub(r"\s+", " ", (text or "")).strip()
    text = text.strip(" .,:;!?-\"'")
    return text[:MAX_FACT_CHARS]


def extract_with_rules(message: str) -> List[str]:
    """Pull facts out of one user message using regex rules only."""
    found = []
    text = message or ""
    for pattern, template in RULES:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            groups = [_tidy(g) for g in match.groups() if g]
            if not groups or any(len(g) < 2 for g in groups):
                continue
            fact = template.format(*groups)
            fact = fact[0].upper() + fact[1:] if fact else fact
            if not fact.endswith("."):
                fact += "."
            if JUNK.match(fact):
                continue
            found.append(fact)
    return found


# --------------------------------------------------------------------------
# AI-assisted extraction
# --------------------------------------------------------------------------
EXTRACTION_PROMPT = """You extract durable facts about the user from a conversation.

Return ONLY a JSON array of short strings. No prose, no code fences.

Include ONLY:
- the user's name, location, job, studies, or skill level
- stable preferences (languages, tools, formatting, how they like answers)
- ongoing projects or goals they mention
- anything they explicitly asked you to remember

Exclude:
- one-off questions or task details
- anything about you (the assistant)
- facts already in the "Already known" list
- guesses or inferences

If there is nothing new and durable, return exactly: []

Already known:
{known}

Conversation:
{conversation}
"""


def _parse_json_facts(raw: str) -> List[str]:
    """Read a JSON array of strings out of a model reply, tolerating stray text."""
    if not raw:
        return []
    text = raw.strip()
    # Strip ``` fences if the model added them anyway.
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    # Grab the outermost [ ... ] block.
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except (ValueError, TypeError):
        return []
    if not isinstance(data, list):
        return []

    facts = []
    for item in data:
        if isinstance(item, str):
            fact = _tidy(item)
            if len(fact) >= 4 and not JUNK.match(fact):
                facts.append(fact if fact.endswith(".") else fact + ".")
    return facts


def extract_with_ai(user_message: str, assistant_reply: str, known: List[str]) -> List[str]:
    """Ask the model for durable facts. Returns [] on any failure."""
    from app.services.ai_service import AIServiceError, ai_service

    conversation = f"User: {user_message}\nAssistant: {assistant_reply[:1500]}"
    prompt = EXTRACTION_PROMPT.format(
        known="\n".join(f"- {k}" for k in known[:40]) or "(nothing yet)",
        conversation=conversation,
    )
    try:
        raw = ai_service.generate_raw(
            [{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.0,
        )
    except AIServiceError as exc:
        logger.info("Memory extraction skipped: %s", exc)
        return []
    except Exception:  # noqa: BLE001
        logger.exception("Memory extraction failed")
        return []
    return _parse_json_facts(raw)


# --------------------------------------------------------------------------
# Storing
# --------------------------------------------------------------------------
def _is_duplicate(fact: str, existing: List[str]) -> bool:
    """Catch near-duplicates, not just exact matches."""
    norm = re.sub(r"[^a-z0-9 ]", "", fact.lower()).strip()
    if not norm:
        return True
    for other in existing:
        other_norm = re.sub(r"[^a-z0-9 ]", "", other.lower()).strip()
        if not other_norm:
            continue
        if norm == other_norm or norm in other_norm or other_norm in norm:
            return True
    return False


def remember(facts: List[str], conversation_id: int = None, source: str = "auto") -> List[str]:
    """Store new facts, skipping duplicates and respecting the cap."""
    if not facts:
        return []

    existing_rows = db.list_memories()
    existing = [r["content"] for r in existing_rows]
    stored = []

    for fact in facts:
        if len(existing) >= settings.MEMORY_MAX_FACTS:
            logger.info("Memory cap of %s reached; not storing more.",
                        settings.MEMORY_MAX_FACTS)
            break
        if _is_duplicate(fact, existing):
            continue
        row = db.add_memory(fact, source=source, source_conversation=conversation_id)
        if row:
            stored.append(fact)
            existing.append(fact)

    if stored:
        logger.info("Learned %s new fact(s): %s", len(stored), stored)
    return stored


def learn_from_exchange(conversation_id: int, user_message: str, assistant_reply: str) -> List[str]:
    """
    Called after every reply. Runs the rules first (free, instant), then the
    AI pass if enabled. Never raises -- memory failing must not break chat.
    """
    if not settings.MEMORY_ENABLED:
        return []
    try:
        facts = extract_with_rules(user_message)

        if settings.MEMORY_AI_EXTRACTION and not settings.AI_OFFLINE_MOCK:
            known = [r["content"] for r in db.list_memories()]
            facts += extract_with_ai(user_message, assistant_reply, known)

        return remember(facts, conversation_id=conversation_id)
    except Exception:  # noqa: BLE001
        logger.exception("learn_from_exchange failed (chat continues normally)")
        return []


# --------------------------------------------------------------------------
# Reading back into the prompt
# --------------------------------------------------------------------------
def format_for_prompt() -> str:
    """Render stored facts as a block for the system prompt."""
    if not settings.MEMORY_ENABLED:
        return ""
    rows = db.list_memories()
    if not rows:
        return ""
    lines = "\n".join(f"- {r['content']}" for r in rows)
    return (
        "## What you know about the user\n"
        "These facts come from earlier conversations. Use them naturally when "
        "relevant. Do not recite them back unless asked.\n"
        f"{lines}"
    )
