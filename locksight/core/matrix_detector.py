"""
Deadlock detection for MULTI-instance resources, using the matrix-based
detection algorithm (Silberschatz, "Operating System Concepts", Ch. 8).

Why a separate algorithm?
  With multi-instance resources, a cycle in the wait-for graph is necessary
  but NOT sufficient for deadlock. A process outside the cycle may hold an
  instance and release it, which breaks the wait. So instead of looking for
  cycles, we simulate: "Can every process eventually finish?"

The algorithm (m resources, n processes):
  1. Work = Available (free instances of each resource)
     Finish[i] = True if process i holds nothing, else False
     (a process holding nothing cannot be blocking anyone)
  2. Find a process i with Finish[i] == False and Request[i] <= Work
     (its pending requests can be satisfied right now)
  3. Pretend it runs to completion and releases everything:
     Work = Work + Allocation[i];  Finish[i] = True;  go to step 2
  4. If no such process exists, stop. Every process with
     Finish[i] == False is deadlocked.

Time complexity: O(m * n^2).
"""

from collections import deque


def find_deadlocked_processes(resource_graph):
    """Return the set of deadlocked processes (matrix algorithm)."""
    g = resource_graph
    work = {rid: g.available(rid) for rid in g.resources}

    finish = {}
    for pid in g.processes:
        holds_something = any(n > 0 for n in g.allocation.get(pid, {}).values())
        finish[pid] = not holds_something

    progress = True
    while progress:
        progress = False
        for pid in g.processes:
            if finish[pid]:
                continue
            requests = g.request.get(pid, {})
            if all(n <= work[rid] for rid, n in requests.items()):
                # pid can get what it needs, finish, and release everything
                for rid, n in g.allocation.get(pid, {}).items():
                    work[rid] += n
                finish[pid] = True
                progress = True

    return {pid for pid, done in finish.items() if not done}


def group_deadlocked(resource_graph, deadlocked):
    """Split a set of deadlocked processes into independent groups.

    Two deadlocked processes are in the same group if they are connected
    in the wait-for graph (in either direction). Recovery can then handle
    each group separately.
    """
    wfg = resource_graph.wait_for_graph()
    neighbours = {pid: set() for pid in deadlocked}
    for pid in deadlocked:
        for other in wfg.get(pid, ()):
            if other in deadlocked:
                neighbours[pid].add(other)
                neighbours[other].add(pid)

    groups, seen = [], set()
    for start in deadlocked:
        if start in seen:
            continue
        group, queue = set(), deque([start])
        seen.add(start)
        while queue:
            node = queue.popleft()
            group.add(node)
            for nxt in neighbours[node]:
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        groups.append(group)
    return groups
