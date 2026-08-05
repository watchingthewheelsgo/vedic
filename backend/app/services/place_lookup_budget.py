from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class PlaceLookupRateLimitError(RuntimeError):
    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = max(1, retry_after_seconds)
        super().__init__("place lookup rate limit exceeded")


class PlaceLookupBudget:
    """Process-local guard for the expensive WebSearch/WebFetch path."""

    def __init__(self, *, limit: int, window_seconds: float, max_concurrent: int) -> None:
        self.limit = max(1, limit)
        self.window_seconds = max(1.0, window_seconds)
        self.max_concurrent = max(1, max_concurrent)
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._active = 0
        self._lock = threading.Lock()

    def acquire(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            events = self._events[key]
            cutoff = now - self.window_seconds
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.limit:
                retry_after = int(max(1, events[0] + self.window_seconds - now))
                raise PlaceLookupRateLimitError(retry_after)
            if self._active >= self.max_concurrent:
                raise PlaceLookupRateLimitError(1)
            events.append(now)
            self._active += 1

    def release(self) -> None:
        with self._lock:
            self._active = max(0, self._active - 1)
