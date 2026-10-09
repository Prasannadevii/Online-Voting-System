"""Sliding-window rate limiter (application layer).

CN CONCEPT: TCP has its own congestion/flow control inside the OS kernel. NetVote does
NOT re-implement that. This is *request-level* rate limiting to protect the server from
floods and password guessing: at most N requests per window per client IP -> HTTP 429.
"""
import threading
import time
from collections import deque


class SlidingWindowLimiter:
    def __init__(self, limit: int, window: float = 60.0, name: str = "limiter"):
        self.limit, self.window, self.name = limit, window, name
        self._hits = {}
        self._lock = threading.Lock()
        self.allowed = self.blocked = 0
        self.events = deque(maxlen=100)
        self._last_flag = {}

    def check(self, key: str):
        """Returns (allowed, retry_after_seconds, remaining)."""
        now = time.monotonic()
        with self._lock:
            q = self._hits.setdefault(key, deque())
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                self.blocked += 1
                retry = max(1, int(self.window - (now - q[0])) + 1)
                return False, retry, 0
            q.append(now)
            self.allowed += 1
            return True, 0, self.limit - len(q)

    def should_flag(self, key: str) -> bool:
        """True once per window per key (so a flood doesn't flood the audit log)."""
        now = time.monotonic()
        with self._lock:
            if now - self._last_flag.get(key, -1e9) > self.window:
                self._last_flag[key] = now
                self.events.append({"time": time.strftime("%H:%M:%S"), "key": key})
                return True
            return False

    def reset(self):
        with self._lock:
            self._hits.clear()
            self._last_flag.clear()
            self.allowed = self.blocked = 0
            self.events.clear()

    def stats(self) -> dict:
        with self._lock:
            now = time.monotonic()
            current = sum(1 for q in self._hits.values() for t in q if now - t <= self.window)
            return {"name": self.name, "limit": self.limit, "window_s": self.window,
                    "allowed": self.allowed, "blocked": self.blocked,
                    "current_window_requests": current, "tracked_clients": len(self._hits),
                    "recent_events": list(self.events)[-10:]}
