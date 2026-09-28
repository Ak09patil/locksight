"""
Workload runner: executes a list of tasks on real threads through LockSight
and measures what happened. Every scenario and every benchmark uses this.

A Task is a sequence of lock steps. Locks are acquired one after another
and HELD (nested), like real code:

    with lock(A):
        work
        with lock(B):
            work
            ...

Metrics collected (these become the tables and graphs in your report):
  completed       tasks that finished
  failed          tasks that were aborted more than max_retries times
  aborts          victims chosen by recovery
  wall_time       seconds from start to the last task finishing
  throughput      completed tasks per second
  wasted_work     seconds of work thrown away by aborts
                  (time from a victim's start to its abort, summed)
  detection_runs  how many times detection ran
  detection_time  total seconds spent inside detection + recovery
"""

import threading
import time
from contextlib import ExitStack
from dataclasses import dataclass, field

from locksight.runtime.locksight import DeadlockVictimError, LockSight


@dataclass
class Step:
    resource: str
    hold_time: float = 0.005   # seconds of "work" after acquiring
    count: int = 1


@dataclass
class Task:
    pid: str
    steps: list
    priority: int = 0


@dataclass
class WorkloadResult:
    scenario: str
    detection: str
    policy: str
    tasks: int
    completed: int
    failed: int
    aborts: int
    wall_time: float
    wasted_work: float
    detection_runs: int
    detection_time: float
    extra: dict = field(default_factory=dict)

    @property
    def throughput(self):
        return self.completed / self.wall_time if self.wall_time else 0.0

    def as_row(self):
        return {
            "scenario": self.scenario, "detection": self.detection,
            "policy": self.policy, "tasks": self.tasks,
            "completed": self.completed, "failed": self.failed,
            "aborts": self.aborts, "wall_time_s": round(self.wall_time, 3),
            "throughput_per_s": round(self.throughput, 1),
            "wasted_work_s": round(self.wasted_work, 3),
            "detection_runs": self.detection_runs,
            "detection_time_ms": round(self.detection_time * 1000, 3),
        }


def run_workload(scenario, resources, tasks, detection="periodic",
                 interval=0.05, policy="weighted", max_retries=50,
                 thread_timeout=60, setup=None):
    """Run tasks concurrently and return a WorkloadResult.

    resources: dict resource_id -> number of instances
    tasks:     list of Task
    setup:     optional fn(sight) called before the run starts, e.g. so the
               dashboard server can register its own event listener
    """
    sight = LockSight(detection=detection, interval=interval, policy=policy)
    for rid, instances in resources.items():
        sight.add_resource(rid, instances)

    # Track wasted work from events: when a process starts, and when aborted.
    started, wasted = {}, [0.0]
    track = threading.Lock()

    def on_event(e):
        with track:
            if e["type"] == "process_start":
                started[e["pid"]] = e["time"]
            elif e["type"] == "abort" and e["pid"] in started:
                wasted[0] += e["time"] - started[e["pid"]]

    sight.on_event(on_event)
    if setup is not None:
        setup(sight)

    completed, failed = [], []

    def make_body(task):
        def body(attempt):
            with ExitStack() as stack:
                for step in task.steps:
                    stack.enter_context(sight.lock(step.resource, step.count))
                    time.sleep(step.hold_time)
        return body

    def worker(task):
        try:
            sight.run(task.pid, make_body(task), priority=task.priority,
                      max_retries=max_retries)
            completed.append(task.pid)
        except DeadlockVictimError:
            failed.append(task.pid)

    threads = [threading.Thread(target=worker, args=(t,), name=t.pid)
               for t in tasks]
    t0 = time.perf_counter()
    with sight:
        for t in threads:
            t.start()
        for t in threads:
            t.join(thread_timeout)
    wall = time.perf_counter() - t0

    stuck = [t.name for t in threads if t.is_alive()]
    if stuck:
        raise RuntimeError(f"Workload did not finish, stuck threads: {stuck}")

    return WorkloadResult(
        scenario=scenario, detection=detection, policy=policy,
        tasks=len(tasks), completed=len(completed), failed=len(failed),
        aborts=sight.stats["aborts"], wall_time=wall, wasted_work=wasted[0],
        detection_runs=sight.stats["detection_runs"],
        detection_time=sight.stats["detection_seconds"],
    )


def print_result(result):
    row = result.as_row()
    width = max(len(k) for k in row)
    print()
    for k, v in row.items():
        print(f"  {k:<{width}}  {v}")
    print()
