"""Thread-pool wrapper with live counters.

OS CONCEPT: THREAD POOL - a fixed set of worker threads executes queued tasks, avoiding
the cost of creating one thread per task and bounding resource use.
"""
import threading
from concurrent.futures import ThreadPoolExecutor


class WorkerPool:
    def __init__(self, max_workers: int = 16, name: str = "netvote-pool"):
        self.max_workers = max_workers
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix=name)
        self._lock = threading.Lock()
        self.submitted = self.completed = self.failed = self.active = 0

    def submit(self, fn, *args, **kwargs):
        with self._lock:
            self.submitted += 1

        def run():
            with self._lock:
                self.active += 1
            try:
                return fn(*args, **kwargs)
            except BaseException:
                with self._lock:
                    self.failed += 1
                raise
            finally:
                with self._lock:
                    self.active -= 1
                    self.completed += 1
        return self._pool.submit(run)

    def stats(self) -> dict:
        with self._lock:
            queued = max(0, self.submitted - self.completed - self.active)
            return {"max_workers": self.max_workers, "submitted": self.submitted,
                    "completed": self.completed, "failed": self.failed,
                    "active_workers": self.active, "queued": queued}

    def shutdown(self):
        self._pool.shutdown(wait=False)


APP_POOL = WorkerPool(16)
