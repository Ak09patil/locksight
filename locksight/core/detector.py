"""
Deadlock detection for single-instance resources using Tarjan's
Strongly Connected Components (SCC) algorithm.

Idea:
  In a wait-for graph (P1 -> P2 means "P1 waits for something P2 holds"),
  when every resource has exactly one instance, a cycle means deadlock.

  A Strongly Connected Component is a group of nodes where every node can
  reach every other node. Any SCC with more than one process contains a
  cycle, so every process in it is deadlocked.

Why Tarjan instead of a simple DFS cycle check?
  - A plain DFS stops at the FIRST cycle it finds.
  - Tarjan finds ALL deadlocked groups in a single pass, in O(V + E) time.
  - This matters when several independent deadlocks exist at once.

This implementation is iterative (uses an explicit stack instead of
recursion), so it won't hit Python's recursion limit on large graphs
(important for the benchmarks with thousands of processes).

Multi-instance resources are handled separately in Step 4, because there
a cycle does NOT guarantee a deadlock.
"""


def find_sccs(graph):
    """Return all strongly connected components of a directed graph.

    graph: dict mapping node -> iterable of neighbour nodes.
    Returns: list of sets, one set per SCC.
    """
    index_of = {}     # node -> order in which DFS first visited it
    lowlink = {}      # node -> smallest index reachable from it
    on_stack = set()  # nodes currently in the SCC stack
    scc_stack = []
    sccs = []
    counter = 0

    for start in graph:
        if start in index_of:
            continue

        # Each work item: (node, iterator over its neighbours)
        work = [(start, iter(graph.get(start, ())))]
        index_of[start] = lowlink[start] = counter
        counter += 1
        scc_stack.append(start)
        on_stack.add(start)

        while work:
            node, neighbours = work[-1]
            advanced = False

            for nxt in neighbours:
                if nxt not in index_of:
                    # Unvisited: go deeper (this replaces a recursive call)
                    index_of[nxt] = lowlink[nxt] = counter
                    counter += 1
                    scc_stack.append(nxt)
                    on_stack.add(nxt)
                    work.append((nxt, iter(graph.get(nxt, ()))))
                    advanced = True
                    break
                elif nxt in on_stack:
                    # Back edge to a node in the current path: cycle found
                    lowlink[node] = min(lowlink[node], index_of[nxt])

            if advanced:
                continue

            # All neighbours done: finish this node
            work.pop()
            if work:
                parent = work[-1][0]
                lowlink[parent] = min(lowlink[parent], lowlink[node])

            # node is the root of an SCC: pop the whole component
            if lowlink[node] == index_of[node]:
                component = set()
                while True:
                    member = scc_stack.pop()
                    on_stack.discard(member)
                    component.add(member)
                    if member == node:
                        break
                sccs.append(component)

    return sccs


def find_deadlocks(resource_graph):
    """Find every deadlocked group of processes.

    resource_graph: a ResourceGraph (all resources single-instance).
    Returns: list of sets, each set is one group of deadlocked processes.
    """
    wfg = resource_graph.wait_for_graph()
    deadlocks = []
    for component in find_sccs(wfg):
        if len(component) > 1:
            deadlocks.append(component)
        else:
            # A single process is only deadlocked if it waits on itself
            (pid,) = component
            if pid in wfg.get(pid, ()):
                deadlocks.append(component)
    return deadlocks
