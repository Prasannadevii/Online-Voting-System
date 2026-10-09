"""Instrumented mutex used to protect the vote critical section.

OS CONCEPT: MUTEX / CRITICAL SECTION
  A mutex lets only one thread at a time execute the code between acquire and release.
  This wrapper counts how often threads had to WAIT (lock contention) so the dashboard
  can show real numbers.

OS CONCEPT: STARVATION / DEADLOCK AVOIDANCE
  Acquisition uses a timeout. A request that cannot get the lock in time fails with 503
  instead of hanging forever. The voting path only ever needs ONE lock, so a circular
  wait (deadlock) is impossible by design.
"""
import threading
import time


class LockTimeout(Exception):
    pass


class InstrumentedLock:
    def __init__(self, name: str = "vote_lock", timeout: float = 10.0):
        self.name, self.timeout = name, timeout
        self._lock = threading.Lock()
        self._stats = threading.Lock()
        self.reset_stats()
        self._held_since = 0.0

    def reset_stats(self):
        with self._stats:
            self.acquisitions = self.contended = self.timeouts = 0
            self.total_wait = self.max_wait = self.total_hold = 0.0
            self.waiting = 0
            self.holder = None

    def __enter__(self):
        t0 = time.perf_counter()
        if self._lock.acquire(blocking=False):
            contended = False
        else:
            contended = True
            with self._stats:
                self.waiting += 1
            got = self._lock.acquire(timeout=self.timeout)
            with self._stats:
                self.waiting -= 1
                if not got:
                    self.timeouts += 1
            if not got:
                raise LockTimeout(f"could not acquire {self.name} within {self.timeout}s")
        waited = time.perf_counter() - t0
        self._held_since = time.perf_counter()
        with self._stats:
            self.acquisitions += 1
            self.contended += int(contended)
            self.total_wait += waited
            self.max_wait = max(self.max_wait, waited)
            self.holder = threading.current_thread().name
        self.last_wait = waited
        return self

    def __exit__(self, *exc):
        held = time.perf_counter() - self._held_since
        with self._stats:
            self.total_hold += held
            self.holder = None
        self._lock.release()
        return False

    def stats(self) -> dict:
        with self._stats:
            n = self.acquisitions or 1
            return {"name": self.name, "acquisitions": self.acquisitions,
                    "contended": self.contended, "timeouts": self.timeouts,
                    "contention_pct": round(100 * self.contended / n, 1),
                    "avg_wait_ms": round(1000 * self.total_wait / n, 3),
                    "max_wait_ms": round(1000 * self.max_wait, 3),
                    "avg_hold_ms": round(1000 * self.total_hold / n, 3),
                    "waiting_now": self.waiting, "locked_now": self._lock.locked(),
                    "holder": self.holder}


# One process-wide lock for the REAL election database.
VOTE_LOCK = InstrumentedLock("vote_lock")
