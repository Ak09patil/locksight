"""
Single entry point for deadlock detection.

Chooses the algorithm automatically:
  - All resources single-instance -> Tarjan SCC on the wait-for graph
    (fast, O(V + E), cycle == deadlock)
  - Any multi-instance resource   -> matrix detection algorithm
    (cycle is not enough, must simulate whether processes can finish)

The rest of LockSight (recovery, dashboard) only calls detect(), so it
never needs to know which algorithm ran.
"""

from dataclasses import dataclass, field

from locksight.core.detector import find_deadlocks
from locksight.core.matrix_detector import find_deadlocked_processes, group_deadlocked


@dataclass
class DetectionResult:
    method: str                                  # "tarjan" or "matrix"
    deadlocks: list = field(default_factory=list)  # list of sets of processes

    @property
    def has_deadlock(self):
        return len(self.deadlocks) > 0


def detect(resource_graph):
    all_single = all(n == 1 for n in resource_graph.resources.values())
    if all_single:
        return DetectionResult("tarjan", find_deadlocks(resource_graph))
    deadlocked = find_deadlocked_processes(resource_graph)
    return DetectionResult("matrix", group_deadlocked(resource_graph, deadlocked))
