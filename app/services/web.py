"""
Phase 4 - Web: let Nova look things up.

Uses DuckDuckGo's HTML endpoint: no API key, no account, no cost. It is
scraped rather than an official API, so it is written defensively and always
degrades to a clear message instead of an exception.

This is how Nova answers "what happened today" questions that a language
model trained months ago cannot know.
"""

import html
import logging
import re
import urllib.parse

logger = logging.getLogger(__name__)

SEARCH_URL = "https://html.duckduckgo.com/html/"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0 Safari/537.36"),
}


class WebError(Exception):
    """A web lookup that failed. Message is safe to show the user."""


def _strip_tags(raw: str) -> str:
    text = re.sub(r"<[^>]+>", "", raw or "")
    return html.unescape(text).strip()


def _unwrap(link: str) -> str:
    """DuckDuckGo wraps results in a redirect; pull the real URL out."""
    if "uddg=" in link:
        try:
            query = urllib.parse.urlparse(link).query
            target = urllib.parse.parse_qs(query).get("uddg", [""])[0]
            if target:
                return target
        except Exception:  # noqa: BLE001
            pass
    if link.startswith("//"):
        return "https:" + link
    return link


def search(query: str, count: int = 5) -> str:
    """Search the web and return a short readable summary of the top hits."""
    term = (query or "").strip()
    if not term:
        raise WebError("Tell me what to search for.")

    count = max(1, min(int(count or 5), 8))

    try:
        import httpx

        response = httpx.post(
            SEARCH_URL, data={"q": term}, headers=HEADERS,
            timeout=20.0, follow_redirects=True,
        )
        response.raise_for_status()
        page = response.text
    except Exception as exc:  # noqa: BLE001
        logger.warning("Web search failed: %s", exc)
        raise WebError(
            "I could not reach the search engine. Check your internet connection."
        ) from exc

    blocks = re.findall(
        r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>'
        r'.*?(?:<a[^>]+class="result__snippet"[^>]*>(.*?)</a>)?',
        page, re.DOTALL,
    )

    results = []
    for link, title_html, snippet_html in blocks:
        title = _strip_tags(title_html)
        if not title:
            continue
        results.append({
            "title": title,
            "url": _unwrap(link),
            "snippet": _strip_tags(snippet_html)[:220],
        })
        if len(results) >= count:
            break

    if not results:
        return (f"I searched for '{term}' but got nothing usable back. "
                "Try different words.")

    lines = [f"Top results for '{term}':", ""]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}")
        if r["snippet"]:
            lines.append(f"   {r['snippet']}")
        lines.append(f"   {r['url']}")
    return "\n".join(lines)
