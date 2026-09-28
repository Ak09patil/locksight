"""
LockSight runtime: instrumented locks for real threads.

Worker threads use sight.lock(...) instead of plain locks. Every request,
acquire and release is recorded in the ResourceGraph, and deadlocks are
detected and broken automatically.

Usage:
    sight = LockSight(detection="periodic", interval=0.1)
    sight.add_resource("inventory:42")
    sight.add_resource("wallet:7")
    sight.start()

    def order_work(attempt):
        with sight.lock("inventory:42"):
            with sight.lock("wallet:7"):
                ...  # do the work

    sight.run("order-svc", order_work, priority=5)   # retries if aborted
    sight.stop()

Key design decisions (important for the viva):

1. ONE condition variable guards the whole graph.
   Every graph change happens while holding it, so the detector always sees
   a consistent snapshot. Waiting threads sleep on it and are woken with
   notify_all() whenever something is released or a victim is aborted.

2. Threads are never killed. Python cannot safely kill a thread, and killing
   one that holds locks would corrupt state. Instead the victim is marked as
   aborted; it is always blocked inside _acquire(), so it wakes up, sees the
   flag, and raises DeadlockVictimError. Its "with" blocks unwind normally.
   Its resources were already released from the graph by recovery, so the
   release calls during unwinding become no-ops.

3. Two detection modes (compared in the benchmarks):
   - "periodic": a background thread runs detection every `interval` seconds
     (low overhead, but a deadlock may last up to one interval).
   - "on_block": detection runs every time a thread has to wait
     (deadlocks are caught instantly, but detection runs far more often).

4. Waits use a short timeout (50 ms) as a safety net, so a missed
   notification can never leave a thread asleep forever.
"""

import random
import threading
import time
from contextlib import contextmanager

from locksight.core.graph import ResourceGraph
from locksight.recovery.manager import RecoveryManager


class DeadlockVictimError(Exception):
    """Raised inside a worker thread chosen as a deadlock victim."""

    def __init__(self, pid):
        super().__init__(f"{pid} was aborted to break a deadlock")
        self.pid = pid


class LockSight:
    def __init__(self, detection="periodic", interval=0.1, policy="weighted",
                 max_victim_count=3):
        if detection not in ("periodic", "on_block"):
            raise ValueError("detection must be 'periodic' or 'on_block'")
        self.detection = detection
        self.interval = interval
        self.graph = ResourceGraph()
        self.recovery = RecoveryManager(policy=policy,
                                        max_victim_count=max_victim_count)

        self._cond = threading.Condition()   # guards graph + everything below
        self._aborted = set()                # victims not yet unwound
        self._start_time = {}                # pid -> when it started (work_done)
        self._local = threading.local()      # which pid this thread runs as
        self._listeners = []
        self._stop_event = threading.Event()
        self._thread = None

        self.stats = {"detection_runs": 0, "detection_seconds": 0.0,
                      "aborts": 0, "retries": 0}

    # ---------- setup ----------

    def add_resource(self, rid, instances=1):
        with self._cond:
            self.graph.add_resource(rid, instances)

    def on_event(self, fn):
        """Register a callback fn(event_dict). Used by the dashboard.
        Callbacks must be fast: some are called while the lock is held."""
        self._listeners.append(fn)

    def snapshot(self):
        with self._cond:
            return self.graph.snapshot()

    # ---------- detector thread ----------

    def start(self):
        if self.detection == "periodic" and self._thread is None:
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._detector_loop,
                                            name="locksight-detector",
                                            daemon=True)
            self._thread.start()
        return self

    def stop(self):
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join()
            self._thread = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()

    def _detector_loop(self):
        while not self._stop_event.wait(self.interval):
            with self._cond:
                self._detect_and_recover()

    # ---------- processes ----------

    @contextmanager
    def process(self, pid, priority=0):
        """Run the current thread as process `pid` for the duration."""
        with self._cond:
            if pid in self.graph.processes:
                raise ValueError(f"Process {pid} is already running")
            self.graph.add_process(pid)
            self._aborted.discard(pid)
            self._start_time[pid] = time.monotonic()
            self.recovery.set_meta(pid, priority=priority, work_done=0.0)
        self._local.pid = pid
        self._emit("process_start", pid=pid)
        try:
            yield
        finally:
            self._local.pid = None
            with self._cond:
                # An aborted process was already removed by recovery.
                if pid in self.graph.processes:
                    self.graph.remove_process(pid)
                self._start_time.pop(pid, None)
                self._cond.notify_all()
            self._emit("process_end", pid=pid)

    def run(self, pid, fn, priority=0, max_retries=10, backoff=0.01):
        """Run fn(attempt) as process `pid`, restarting it if it is aborted.
        attempt is 0 on the first run, 1 after the first abort, and so on."""
        for attempt in range(max_retries + 1):
            try:
                with self.process(pid, priority=priority):
                    return fn(attempt)
            except DeadlockVictimError:
                with self._cond:
                    self.stats["retries"] += 1
                self._emit("retry", pid=pid, attempt=attempt + 1)
                # Random jitter so restarted processes don't collide in the
                # same order again (avoids livelock).
                time.sleep(backoff * (attempt + 1) * random.uniform(0.5, 1.5))
        raise DeadlockVictimError(pid)

    # ---------- locks ----------

    @contextmanager
    def lock(self, rid, count=1):
        pid = getattr(self._local, "pid", None)
        if pid is None:
            raise RuntimeError("sight.lock() must be used inside sight.process()"
                               " or sight.run()")
        self._acquire(pid, rid, count)
        try:
            yield
        finally:
            self._release(pid, rid, count)

    def _acquire(self, pid, rid, count):
        with self._cond:
            self._check_aborted(pid)
            self.graph.request_resource(pid, rid, count)

            if self.graph.available(rid) < count:
                self._emit("wait", pid=pid, resource=rid, count=count)
                if self.detection == "on_block":
                    self._detect_and_recover()

            while True:
                self._check_aborted(pid)
                if self.graph.available(rid) >= count:
                    self.graph.grant(pid, rid, count)
                    # Emitted while holding the lock so the event order
                    # always matches the real order of graph changes.
                    self._emit("acquire", pid=pid, resource=rid, count=count)
                    break
                self._cond.wait(timeout=0.05)

    def _release(self, pid, rid, count):
        with self._cond:
            if pid in self._aborted:
                return  # recovery already released everything it held
            self.graph.release(pid, rid, count)
            self._emit("release", pid=pid, resource=rid, count=count)
            self._cond.notify_all()

    def _check_aborted(self, pid):
        if pid in self._aborted:
            raise DeadlockVictimError(pid)

    # ---------- detection + recovery (caller holds self._cond) ----------

    def _detect_and_recover(self):
        now = time.monotonic()
        for pid, started in self._start_time.items():
            if pid in self.graph.processes:
                self.recovery.set_meta(pid, work_done=now - started)

        t0 = time.perf_counter()
        actions = self.recovery.recover(self.graph)
        self.stats["detection_runs"] += 1
        self.stats["detection_seconds"] += time.perf_counter() - t0

        for action in actions:
            self._aborted.add(action.victim)
            self.stats["aborts"] += 1
            self._emit("abort", pid=action.victim,
                       group=sorted(str(p) for p in action.group),
                       method=action.method, policy=action.policy,
                       released=action.released)
        if actions:
            self._cond.notify_all()  # wake the victim and anyone now unblocked
        return actions

    # ---------- events ----------

    def _emit(self, type_, **data):
        event = {"type": type_, "time": time.time(), **data}
        for fn in self._listeners:
            try:
                fn(event)
            except Exception:
                pass  # a broken listener must never break locking
