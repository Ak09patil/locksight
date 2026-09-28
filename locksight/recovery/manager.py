"""
Recovery manager: detects deadlocks and breaks them by aborting victims.

Strategy: abort one process at a time, then detect again (the textbook
"abort one process at a time until the deadlock cycle is eliminated").
Aborting only ONE victim per group, instead of the whole group, wastes the
least work.

Every abort is recorded as a RecoveryAction, which the dashboard and the
report's results section will use later.
"""

from dataclasses import dataclass, field

from locksight.core.detect import detect
from locksight.recovery.policies import ProcessMeta, choose_victim


@dataclass
class RecoveryAction:
    victim: object
    group: set                 # the deadlocked group the victim came from
    policy: str
    method: str                # detection method used: "tarjan" or "matrix"
    released: dict = field(default_factory=dict)  # resource -> instances freed


class RecoveryManager:
    def __init__(self, policy="weighted", max_victim_count=3, max_rounds=1000):
        self.policy = policy
        self.max_victim_count = max_victim_count
        self.max_rounds = max_rounds  # safety guard against infinite loops
        self.meta = {}                # pid -> ProcessMeta
        self.history = []             # every RecoveryAction ever taken

    def meta_of(self, pid):
        """Metadata for a process, created with defaults if unknown.
        Kept even after a process is aborted, so a restarted process with
        the same id keeps its victim_count (starvation protection)."""
        if pid not in self.meta:
            self.meta[pid] = ProcessMeta()
        return self.meta[pid]

    def set_meta(self, pid, priority=None, work_done=None):
        m = self.meta_of(pid)
        if priority is not None:
            m.priority = priority
        if work_done is not None:
            m.work_done = work_done

    def abort(self, graph, pid):
        """Abort a process: release everything it holds and remove it."""
        released = dict(graph.allocation.get(pid, {}))
        graph.remove_process(pid)
        self.meta_of(pid).victim_count += 1
        return released

    def recover(self, graph):
        """Break every deadlock in the graph.
        Returns the list of RecoveryActions taken in this call."""
        actions = []
        for _ in range(self.max_rounds):
            result = detect(graph)
            if not result.has_deadlock:
                return actions

            # One victim per independent group, then re-detect:
            # aborting one process may already have fixed other groups.
            group = result.deadlocks[0]
            victim = choose_victim(graph, group, self.meta_of,
                                   self.policy, self.max_victim_count)
            released = self.abort(graph, victim)
            action = RecoveryAction(victim, set(group), self.policy,
                                    result.method, released)
            actions.append(action)
            self.history.append(action)

        raise RuntimeError("Recovery did not converge within max_rounds")
