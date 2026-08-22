"""
Conversation title generation using plain text processing (no extra AI call).

"How does Java inheritance work?"  ->  "Java Inheritance Work"
"""

import re

# Common words that make poor titles.
STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "so", "of", "in", "on",
    "at", "to", "for", "with", "about", "from", "by", "is", "are", "was", "were",
    "be", "been", "being", "do", "does", "did", "can", "could", "should", "would",
    "will", "shall", "may", "might", "must", "how", "what", "why", "when", "where",
    "who", "which", "please", "help", "me", "my", "i", "you", "your", "it", "its",
    "this", "that", "these", "those", "explain", "tell", "give", "want", "need",
    "some", "any", "there",
}

MAX_TITLE_CHARS = 40
MAX_TITLE_WORDS = 5


def make_title(message: str) -> str:
    """Build a short, human-readable title from the first user message."""
    text = (message or "").strip()
    if not text:
        return "New Chat"

    # Use the first line only, and drop code fences / markdown noise.
    first_line = text.splitlines()[0]
    first_line = re.sub(r"`{1,3}[^`]*`{1,3}", " ", first_line)
    first_line = re.sub(r"[#*_>~\[\]()]", " ", first_line)

    words = re.findall(r"[A-Za-z0-9+#.\-]+", first_line)
    if not words:
        return "New Chat"

    keywords = [w for w in words if w.lower() not in STOPWORDS]
    chosen = (keywords or words)[:MAX_TITLE_WORDS]

    title_words = []
    for word in chosen:
        # Keep acronyms and things like "SQL", "C++", "JavaScript" intact.
        if word.isupper() or any(ch.isupper() for ch in word[1:]):
            title_words.append(word)
        else:
            title_words.append(word.capitalize())

    title = " ".join(title_words).strip(" .-")
    if len(title) > MAX_TITLE_CHARS:
        title = title[:MAX_TITLE_CHARS].rsplit(" ", 1)[0] + "…"
    return title or "New Chat"
