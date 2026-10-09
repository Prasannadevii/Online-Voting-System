"""Real request statistics (thread-safe, in memory).

Everything shown on the Network Monitor / Performance dashboards is computed from the
requests this process actually served. Nothing is random or hard-coded.

Definitions
  active connections  = requests currently being served (in-flight)
  failed              = HTTP status >= 400
  error rate          = failed / total
  network reliability = share of requests that did NOT end in a 5xx error or a timeout
"""
import threading
import time
from collections import Counter, deque


class NetworkMonitor:
    def __init__(self):
        self._lock = threading.Lock()
        self.started = time.time()
        self.host, self.port = "127.0.0.1", 5000
        self.reset()

    def set_server(self, host, port):
        self.host, self.port = host, port

    def reset(self):
        with self._lock:
            self.total = self.success = self.failed = self.server_errors = 0
            self.timeouts = self.rate_limited = 0
            self.inflight = self.peak_inflight = 0
            self.status_counts = Counter()
            self.latencies = deque(maxlen=2000)
            self.min_ms = self.max_ms = None
            self.sum_ms = 0.0
            self.buckets = {}      # epoch second -> dict
            self.recent = deque(maxlen=60)

    def request_started(self):
        with self._lock:
            self.inflight += 1
            self.peak_inflight = max(self.peak_inflight, self.inflight)

    def request_finished(self, method, path, status, ms, ip="", request_id=""):
        sec = int(time.time())
        with self._lock:
            self.inflight = max(0, self.inflight - 1)
            self.total += 1
            self.status_counts[status] += 1
            if status < 400:
                self.success += 1
            else:
                self.failed += 1
            if status >= 500:
                self.server_errors += 1
            if status == 429:
                self.rate_limited += 1
            self.latencies.append(ms)
            self.sum_ms += ms
            self.min_ms = ms if self.min_ms is None else min(self.min_ms, ms)
            self.max_ms = ms if self.max_ms is None else max(self.max_ms, ms)
            b = self.buckets.setdefault(sec, {"n": 0, "err": 0, "ms": 0.0, "ok": 0,
                                              "rl": 0, "to": 0, "inflight": 0})
            b["n"] += 1
            b["ms"] += ms
            b["inflight"] = max(b["inflight"], self.inflight + 1)
            if status >= 400:
                b["err"] += 1
            else:
                b["ok"] += 1
            if status == 429:
                b["rl"] += 1
            for old in [k for k in self.buckets if k < sec - 900]:
                del self.buckets[old]
            self.recent.appendleft({"time": time.strftime("%H:%M:%S"), "method": method,
                                    "path": path, "status": status, "ms": round(ms, 1),
                                    "request_id": request_id})

    def record_timeout(self):
        with self._lock:
            self.timeouts += 1
            b = self.buckets.setdefault(int(time.time()), {"n": 0, "err": 0, "ms": 0.0, "ok": 0,
                                                           "rl": 0, "to": 0, "inflight": 0})
            b["to"] += 1

    @staticmethod
    def _pct(sorted_vals, p):
        if not sorted_vals:
            return 0.0
        k = min(len(sorted_vals) - 1, int(round(p / 100 * (len(sorted_vals) - 1))))
        return sorted_vals[k]

    def snapshot(self) -> dict:
        now = int(time.time())
        with self._lock:
            lat = sorted(self.latencies)
            last10 = sum(self.buckets.get(s, {}).get("n", 0) for s in range(now - 9, now + 1))
            total = self.total or 1
            reliability = 100.0 - 100.0 * (self.server_errors + self.timeouts) / total
            return {
                "status": "ONLINE", "host": self.host, "port": self.port,
                "protocol": "HTTP/1.1 over TCP",
                "uptime_s": int(time.time() - self.started),
                "active_connections": self.inflight, "peak_connections": self.peak_inflight,
                "requests_per_second": round(last10 / 10, 2),
                "total_requests": self.total, "successful": self.success, "failed": self.failed,
                "server_errors": self.server_errors, "timeouts": self.timeouts,
                "rate_limited": self.rate_limited,
                "avg_ms": round(self.sum_ms / total, 2) if self.total else 0,
                "fastest_ms": round(self.min_ms, 2) if self.min_ms is not None else 0,
                "slowest_ms": round(self.max_ms, 2) if self.max_ms is not None else 0,
                "p50_ms": round(self._pct(lat, 50), 2), "p95_ms": round(self._pct(lat, 95), 2),
                "p99_ms": round(self._pct(lat, 99), 2),
                "error_rate_pct": round(100 * self.failed / total, 2) if self.total else 0,
                "reliability_pct": round(reliability, 2) if self.total else 100.0,
                "status_codes": {str(k): v for k, v in sorted(self.status_counts.items())},
                "recent": list(self.recent)[:15],
            }

    def series(self, seconds: int = 90) -> dict:
        now = int(time.time())
        out = {"labels": [], "rps": [], "avg_ms": [], "ok": [], "err": [], "timeouts": [],
               "rate_limited": [], "inflight": [], "error_rate": []}
        with self._lock:
            for s in range(now - seconds + 1, now + 1):
                b = self.buckets.get(s)
                out["labels"].append(time.strftime("%H:%M:%S", time.localtime(s)))
                n = b["n"] if b else 0
                out["rps"].append(n)
                out["avg_ms"].append(round(b["ms"] / n, 2) if n else 0)
                out["ok"].append(b["ok"] if b else 0)
                out["err"].append(b["err"] if b else 0)
                out["timeouts"].append(b["to"] if b else 0)
                out["rate_limited"].append(b["rl"] if b else 0)
                out["inflight"].append(b["inflight"] if b else 0)
                out["error_rate"].append(round(100 * b["err"] / n, 1) if b and n else 0)
        return out


MONITOR = NetworkMonitor()
