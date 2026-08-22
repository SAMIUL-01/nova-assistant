"""
Simple in-memory rate limiting (spec section 29).

Protects the expensive endpoints from a runaway loop, a stuck retry, or abuse
if you ever expose the app publicly.

Implemented as a FastAPI dependency rather than middleware on purpose:
middleware that wraps responses can buffer Server-Sent Events, which would
break streaming replies. A dependency runs before the handler and never
touches the response.

Deliberately dependency-free: a sliding window kept in memory, which is the
right size for a personal, single-process app. If you ever run several
workers, move this to Redis -- each process keeps its own counts.

Set RATE_LIMIT_PER_MINUTE=0 in .env to turn it off.
"""

import logging
import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, Request

from app.config import settings

logger = logging.getLogger(__name__)

WINDOW_SECONDS = 60


class RateLimiter:
    """Sliding-window request counter, keyed by client IP."""

    def __init__(self, limit_per_minute: int):
        self.limit = limit_per_minute
        self._hits = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str):
        """Return (allowed, retry_after_seconds, remaining)."""
        if self.limit <= 0:              # 0 or less = disabled
            return True, 0, -1

        now = time.monotonic()
        cutoff = now - WINDOW_SECONDS

        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] < cutoff:
                hits.popleft()

            if len(hits) >= self.limit:
                retry_after = max(1, int(WINDOW_SECONDS - (now - hits[0])) + 1)
                return False, retry_after, 0

            hits.append(now)

            # Stop the dict growing forever on a long-running server.
            if len(self._hits) > 1000:
                for stale in [k for k, v in self._hits.items() if not v]:
                    del self._hits[stale]

            return True, 0, self.limit - len(hits)

    def reset(self):
        """Clear all counters (used by the tests)."""
        with self._lock:
            self._hits.clear()


limiter = RateLimiter(settings.RATE_LIMIT_PER_MINUTE)


def client_key(request: Request) -> str:
    """
    Identify the caller.

    Behind a host like Render or Fly the real IP arrives in X-Forwarded-For,
    so prefer that and fall back to the socket address.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce_rate_limit(request: Request) -> None:
    """FastAPI dependency: raises 429 when the caller is going too fast."""
    allowed, retry_after, _ = limiter.check(client_key(request))
    if not allowed:
        logger.warning("Rate limit hit by %s on %s", client_key(request), request.url.path)
        raise HTTPException(
            status_code=429,
            detail=(
                "You're sending messages very quickly. "
                f"Please wait {retry_after} seconds and try again."
            ),
            headers={"Retry-After": str(retry_after)},
        )
