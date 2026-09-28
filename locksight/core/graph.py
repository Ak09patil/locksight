"""
Resource Allocation Graph (RAG) model for LockSight.

The graph has two kinds of nodes:
  - Processes (P): workers that acquire resources
  - Resources (R): lockable things, each with one or more identical instances

And two kinds of edges:
  - Allocation edge  R -> P : P currently HOLDS some instances of R
  - Request edge     P -> R : P is WAITING for some instances of R

This module is intentionally pure (no threads, no I/O) so it can be tested
in isolation. Thread-safety is handled by the runtime layer that uses it.
"""

from collections import defaultdict


class GraphError(Exception):
    """Raised when an operation would put the graph in an invalid state."""


class ResourceGraph:
    def __init__(self):
        self.processes = set()
        self.resources = {}  # resource_id -> total number of instances
        # allocation[pid][rid] = instances of rid held by pid
        self.allocation = defaultdict(lambda: defaultdict(int))
        # request[pid][rid] = instances of rid pid is waiting for
        self.request = defaultdict(lambda: defaultdict(int))

        # Reverse index, kept in sync with allocation:
        #   held_by[rid][pid] = instances of rid held by pid
        #   allocated[rid]    = total instances of rid currently held
        # Without it, holders() and available() had to scan every process,
        # which made building the wait-for graph O(n^2). Benchmarks exposed
        # this; with the index both are fast lookups.
        self.held_by = defaultdict(dict)
        self.allocated = defaultdict(int)

    # ---------- nodes ----------

    def add_process(self, pid):
        self.processes.add(pid)

    def add_resource(self, rid, instances=1):
        if instances < 1:
            raise GraphError(f"Resource {rid} must have at least 1 instance")
        self.resources[rid] = instances

    def remove_process(self, pid):
        """Remove a process and release everything it holds or waits for.
        Used by recovery when a victim is aborted."""
        self._require_process(pid)
        for rid, n in self.allocation.pop(pid, {}).items():
            self.held_by[rid].pop(pid, None)
            self.allocated[rid] -= n
        self.request.pop(pid, None)
        self.processes.discard(pid)

    # ---------- queries ----------

    def available(self, rid):
        """Free instances of a resource = total - everything allocated."""
        self._require_resource(rid)
        return self.resources[rid] - self.allocated[rid]

    def holders(self, rid):
        """Processes currently holding at least one instance of rid."""
        return set(self.held_by.get(rid, ()))

    def is_waiting(self, pid):
        return any(n > 0 for n in self.request.get(pid, {}).values())

    # ---------- edge operations ----------

    def request_resource(self, pid, rid, count=1):
        """Add a request edge P -> R (process starts waiting)."""
        self._require_process(pid)
        self._require_resource(rid)
        already_held = self.allocation[pid].get(rid, 0)
        if already_held + self.request[pid][rid] + count > self.resources[rid]:
            raise GraphError(f"{pid} requested more of {rid} than exists")
        self.request[pid][rid] += count

    def grant(self, pid, rid, count=1):
        """Convert a request edge into an allocation edge (process acquires)."""
        self._require_process(pid)
        self._require_resource(rid)
        if self.request[pid].get(rid, 0) < count:
            raise GraphError(f"{pid} has no pending request for {count} of {rid}")
        if self.available(rid) < count:
            raise GraphError(f"Only {self.available(rid)} of {rid} available")
        self.request[pid][rid] -= count
        if self.request[pid][rid] == 0:
            del self.request[pid][rid]
        self.allocation[pid][rid] += count
        self.held_by[rid][pid] = self.allocation[pid][rid]
        self.allocated[rid] += count

    def release(self, pid, rid, count=1):
        """Remove an allocation edge (process releases)."""
        self._require_process(pid)
        if self.allocation[pid].get(rid, 0) < count:
            raise GraphError(f"{pid} does not hold {count} of {rid}")
        self.allocation[pid][rid] -= count
        self.allocated[rid] -= count
        if self.allocation[pid][rid] == 0:
            del self.allocation[pid][rid]
            del self.held_by[rid][pid]
        else:
            self.held_by[rid][pid] = self.allocation[pid][rid]

    # ---------- derived views ----------

    def wait_for_graph(self):
        """Collapse the RAG into a wait-for graph: P1 -> P2 means P1 waits
        for a resource that P2 holds. For single-instance resources, a cycle
        here is exactly a deadlock."""
        wfg = {pid: set() for pid in self.processes}
        for pid, reqs in self.request.items():
            for rid, n in reqs.items():
                if n > 0:
                    wfg[pid] |= self.holders(rid) - {pid}
        return wfg

    def snapshot(self):
        """Plain-dict copy of the graph, used later by the dashboard."""
        return {
            "processes": sorted(self.processes),
            "resources": dict(self.resources),
            "allocation": {p: dict(a) for p, a in self.allocation.items() if a},
            "request": {p: dict(r) for p, r in self.request.items() if r},
        }

    # ---------- validation helpers ----------

    def _require_process(self, pid):
        if pid not in self.processes:
            raise GraphError(f"Unknown process {pid}")

    def _require_resource(self, rid):
        if rid not in self.resources:
            raise GraphError(f"Unknown resource {rid}")
