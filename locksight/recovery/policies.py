"""
Victim selection policies for deadlock recovery.

When a deadlock is found, we break it by aborting one process (the
"victim"), which releases everything it holds. Which process should we
pick? The textbook (Silberschatz, Ch. 8) lists the factors:
  - Priority of the process
  - How much work it has already done (aborting it wastes that work)
  - How many resources it holds (aborting it frees more)
  - How many times it has already been a victim (starvation)

Each policy below gives every candidate a COST. The process with the
LOWEST cost is chosen as the victim ("cheapest to abort").

Starvation protection:
  If the same process is always the cheapest, it could be aborted forever
  and never finish. So every process has a victim_count, and once it reaches
  max_victim_count it is protected (skipped) as long as another candidate
  exists. This is applied by choose_victim() for every policy.
"""

from dataclasses import dataclass


@dataclass
class ProcessMeta:
    """Extra information about a process that the graph does not store."""
    priority: int = 0        # higher = more important, less likely victim
    work_done: float = 0.0   # e.g. seconds of work completed so far
    victim_count: int = 0    # times this process was already aborted


def resources_held(graph, pid):
    return sum(graph.allocation.get(pid, {}).values())


# ---------- policies: each returns a cost, lower = better victim ----------

def lowest_priority(graph, pid, meta):
    return meta.priority


def least_work(graph, pid, meta):
    return meta.work_done


def most_resources(graph, pid, meta):
    # Aborting the process that holds the MOST frees the most resources,
    # so more resources held = lower cost.
    return -resources_held(graph, pid)


def weighted(graph, pid, meta, w_priority=1.0, w_work=1.0, w_resources=1.0,
             w_victim=2.0):
    """Combined cost used as the default. Considers every factor at once.
    victim_count RAISES the cost, so repeat victims are avoided naturally."""
    return (w_priority * meta.priority
            + w_work * meta.work_done
            - w_resources * resources_held(graph, pid)
            + w_victim * meta.victim_count)


POLICIES = {
    "lowest_priority": lowest_priority,
    "least_work": least_work,
    "most_resources": most_resources,
    "weighted": weighted,
}


def choose_victim(graph, group, meta_of, policy="weighted", max_victim_count=3):
    """Pick one victim from a deadlocked group.

    graph:     the ResourceGraph
    group:     set of deadlocked process ids
    meta_of:   function pid -> ProcessMeta
    policy:    name from POLICIES
    Returns:   the chosen process id
    """
    cost_fn = POLICIES[policy]

    # Starvation protection: skip processes aborted too often,
    # unless every process in the group has hit the limit.
    candidates = [p for p in group if meta_of(p).victim_count < max_victim_count]
    if not candidates:
        candidates = list(group)

    # Sort key: cost first, then fewer past aborts, then pid so the choice
    # is deterministic (important for repeatable tests and benchmarks).
    return min(candidates,
               key=lambda p: (cost_fn(graph, p, meta_of(p)),
                              meta_of(p).victim_count,
                              str(p)))
