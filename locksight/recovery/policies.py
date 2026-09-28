"""
Victim selection policies for deadlock recovery.

When a deadlock is found, we break it by aborting one process (the
"victim"), which releases everything it holds. Which process should we
pick? The textbook (Silberschatz, Ch. 8) lists the factors:
  - Priority of the process
  - How much work it has already done (aborting it wastes that work)
  - How many resources it holds (aborting it frees more)
  - How many times it has already been a victim (starvation)

"weighted" (the default) combines all four. Its first version,
"weighted_raw", mixed factors with different units; benchmarks showed
priority dominated, so "weighted" now normalises each factor first.

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


def weighted_raw(graph, pid, meta, w_priority=1.0, w_work=1.0,
                 w_resources=1.0, w_victim=2.0):
    """First version of the combined policy, kept for comparison.

    PROBLEM (found in benchmarks): the factors are on different scales.
    Priority is 0-9 but work_done is usually a fraction of a second, so
    priority drowns out everything else and this behaves almost exactly
    like lowest_priority."""
    return (w_priority * meta.priority
            + w_work * meta.work_done
            - w_resources * resources_held(graph, pid)
            + w_victim * meta.victim_count)


def weighted_costs(graph, candidates, meta_of, w_priority=1.0, w_work=1.0,
                   w_resources=1.0, w_victim=1.0):
    """Improved combined policy: min-max normalise each factor to 0..1
    WITHIN the deadlocked group, then combine.

    After normalisation every factor has the same influence, whatever its
    units, so the weights mean what they say. Returns {pid: cost}."""
    def normalise(values):
        lo, hi = min(values.values()), max(values.values())
        if hi == lo:
            return {p: 0.0 for p in values}
        return {p: (v - lo) / (hi - lo) for p, v in values.items()}

    prio = normalise({p: meta_of(p).priority for p in candidates})
    work = normalise({p: meta_of(p).work_done for p in candidates})
    held = normalise({p: resources_held(graph, p) for p in candidates})
    past = normalise({p: meta_of(p).victim_count for p in candidates})
    return {p: (w_priority * prio[p] + w_work * work[p]
                - w_resources * held[p] + w_victim * past[p])
            for p in candidates}


POLICIES = {
    "lowest_priority": lowest_priority,
    "least_work": least_work,
    "most_resources": most_resources,
    "weighted_raw": weighted_raw,
    "weighted": None,   # group-aware, computed by weighted_costs()
}


def choose_victim(graph, group, meta_of, policy="weighted", max_victim_count=3):
    """Pick one victim from a deadlocked group.

    graph:     the ResourceGraph
    group:     set of deadlocked process ids
    meta_of:   function pid -> ProcessMeta
    policy:    name from POLICIES
    Returns:   the chosen process id
    """
    if policy not in POLICIES:
        raise ValueError(f"Unknown policy {policy}")

    # Starvation protection: skip processes aborted too often,
    # unless every process in the group has hit the limit.
    candidates = [p for p in group if meta_of(p).victim_count < max_victim_count]
    if not candidates:
        candidates = list(group)

    # Sort key: cost first, then fewer past aborts, then pid so the choice
    # is deterministic (important for repeatable tests and benchmarks).
    if policy == "weighted":
        costs = weighted_costs(graph, candidates, meta_of)
        cost = costs.__getitem__
    else:
        cost_fn = POLICIES[policy]
        cost = lambda p: cost_fn(graph, p, meta_of(p))  # noqa: E731

    return min(candidates,
               key=lambda p: (cost(p), meta_of(p).victim_count, str(p)))
