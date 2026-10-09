"""EDUCATIONAL SIMULATIONS: deadlock and starvation. Isolated from the voting system.

The real voting path uses exactly ONE lock, so a circular wait cannot occur there.
"""
import threading
import time


# ----------------------------------------------------------------------------- DEADLOCK
def run_deadlock(strategy: str = "deadlock") -> dict:
    """strategy: deadlock | lock_ordering | timeout_backoff | try_lock.
    Two real threads A and B use two real locks R1 and R2. Every wait has a timeout, so the
    demo can never hang the server."""
    r1, r2 = threading.Lock(), threading.Lock()
    ev, evl, t0 = [], threading.Lock(), time.perf_counter()
    barrier = threading.Barrier(2, timeout=5)
    done = {}

    def log(who, msg):
        with evl:
            ev.append({"t_ms": round((time.perf_counter() - t0) * 1000, 1), "thread": who, "op": msg})

    def worker(who, first, second, f_name, s_name, backoff):
        try:
            barrier.wait()
        except threading.BrokenBarrierError:
            pass
        if strategy == "lock_ordering":              # everybody takes R1 before R2
            first, second, f_name, s_name = r1, r2, "R1", "R2"
        attempts = 0
        while attempts < 4:
            attempts += 1
            first.acquire()
            log(who, f"acquired {f_name}")
            time.sleep(0.15)                          # hold it long enough for the other thread
            log(who, f"waiting for {s_name}...")
            if strategy == "try_lock":
                got = second.acquire(blocking=False)
            else:
                got = second.acquire(timeout=1.0)
            if got:
                log(who, f"acquired {s_name} -> critical work done")
                second.release(); first.release()
                log(who, "released both locks")
                done[who] = "completed"
                return
            if strategy == "deadlock":
                log(who, f"STUCK: {s_name} is held by the other thread (circular wait)")
                first.release()
                done[who] = "deadlocked"
                return
            log(who, f"could not get {s_name}: release {f_name}, back off {int(backoff * 1000)} ms, retry")
            first.release()
            time.sleep(backoff)
        done[who] = "gave up"

    ta = threading.Thread(target=worker, args=("Process A", r1, r2, "R1", "R2", 0.05))
    tb = threading.Thread(target=worker, args=("Process B", r2, r1, "R2", "R1", 0.4))
    ta.start(); tb.start(); ta.join(15); tb.join(15)
    deadlocked = "deadlocked" in done.values()
    explain = {
        "deadlock": "All four Coffman conditions held: mutual exclusion, hold-and-wait, no pre-emption, circular wait.",
        "lock_ordering": "Prevention: a global lock order (R1 then R2) breaks the circular-wait condition.",
        "timeout_backoff": "Avoidance: wait with a timeout, release what you hold, back off differently, retry.",
        "try_lock": "Avoidance: non-blocking try-lock - never wait while holding a lock; release and retry.",
    }[strategy]
    return {"strategy": strategy, "events": sorted(ev, key=lambda e: e["t_ms"]), "outcome": done,
            "deadlock_detected": deadlocked,
            "result": "DEADLOCK DETECTED" if deadlocked else "NO DEADLOCK - both processes finished",
            "explanation": explain}


# --------------------------------------------------------------------------- STARVATION
def run_starvation(high_jobs: int = 12) -> dict:
    """Discrete-time single-CPU scheduling simulation (not threads). One low-priority job
    arrives at t=1; a high-priority job arrives EVERY tick. Compare three policies."""
    def simulate(policy):
        jobs = [{"id": "H0", "arrive": 0, "burst": 1, "prio": 5}, {"id": "LOW", "arrive": 1, "burst": 2, "prio": 1}]
        jobs += [{"id": f"H{i}", "arrive": i, "burst": 1, "prio": 5} for i in range(1, high_jobs + 1)]
        t, queue_, finished, timeline = 0, [], {}, []
        pending = sorted(jobs, key=lambda j: j["arrive"])
        while pending or queue_:
            while pending and pending[0]["arrive"] <= t:
                j = pending.pop(0); j["waited"] = 0; queue_.append(j)
            if not queue_:
                t += 1; continue
            if policy == "fifo":
                job = min(queue_, key=lambda j: j["arrive"])
            elif policy == "priority":
                job = max(queue_, key=lambda j: (j["prio"], -j["arrive"]))
            else:                                       # priority + aging
                job = max(queue_, key=lambda j: (j["prio"] + j["waited"] // 2, -j["arrive"]))
            queue_.remove(job)
            timeline.append({"start": t, "end": t + job["burst"], "job": job["id"]})
            for other in queue_:
                other["waited"] += job["burst"]
            t += job["burst"]
            finished[job["id"]] = {"finish": t, "wait": t - job["arrive"] - job["burst"]}
        return {"policy": policy, "timeline": timeline, "low_priority_wait": finished["LOW"]["wait"],
                "low_priority_finish": finished["LOW"]["finish"],
                "avg_wait": round(sum(f["wait"] for f in finished.values()) / len(finished), 2)}

    runs = [simulate(p) for p in ("priority", "fifo", "aging")]
    return {"label": "EDUCATIONAL SIMULATION - discrete-time scheduler, not connected to voting",
            "high_priority_jobs": high_jobs, "policies": runs,
            "explanation": "Strict priority lets the LOW job wait until every HIGH job is done (starvation). "
                           "FIFO and priority-with-aging bound its wait. NetVote's vote lock uses a timeout so "
                           "a request fails fast (503) rather than waiting indefinitely."}
