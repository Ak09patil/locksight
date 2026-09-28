"""
Scenario generators. Each returns (resources, tasks) for run_workload().

All generators take a seed, so the same workload can be replayed exactly
when comparing detection modes and victim policies. (Thread timing still
varies a little between runs, which is why benchmarks repeat each run.)
"""

import random

from locksight.simulator.workload import Step, Task


def bank_transfers(accounts=10, transfers=40, hold_time=0.005,
                   ordered=False, seed=42):
    """Money transfers between accounts. Each transfer locks the source
    account, then the destination account.

    Transfer A->B and transfer B->A at the same time = deadlock.

    ordered=True locks accounts in a fixed global order (lowest id first).
    This is deadlock PREVENTION (breaking the circular-wait condition),
    used as a baseline to compare against detection + recovery.
    """
    rng = random.Random(seed)
    resources = {f"acct:{i}": 1 for i in range(accounts)}
    tasks = []
    for n in range(transfers):
        src, dst = rng.sample(range(accounts), 2)
        order = sorted([src, dst]) if ordered else [src, dst]
        steps = [Step(f"acct:{a}", hold_time) for a in order]
        tasks.append(Task(f"transfer-{n}", steps, priority=rng.randint(0, 9)))
    return resources, tasks


def dining_philosophers(n=5, rounds=3, hold_time=0.01):
    """The classic problem: n philosophers, n forks. Each picks up the left
    fork, then the right. If all pick up their left fork together, every
    philosopher waits forever: one n-process cycle.

    Each philosopher eats `rounds` times (one task per meal)."""
    resources = {f"fork:{i}": 1 for i in range(n)}
    tasks = []
    for r in range(rounds):
        for i in range(n):
            left, right = f"fork:{i}", f"fork:{(i + 1) % n}"
            tasks.append(Task(f"phil-{i}-meal-{r}",
                              [Step(left, hold_time), Step(right, hold_time)]))
    return resources, tasks


def connection_pool(workers=6, pool_size=4, hold_time=0.01):
    """Backend workers sharing a pool of DB connections. Each worker takes
    one connection, then needs a second one (for example, to run a query on
    a second shard). If every connection is held by a worker waiting for a
    second one, all workers are stuck. Multi-instance -> matrix detection."""
    resources = {"db-pool": pool_size}
    tasks = [Task(f"worker-{i}",
                  [Step("db-pool", hold_time), Step("db-pool", hold_time)])
             for i in range(workers)]
    return resources, tasks


def random_stress(processes=30, resources=10, max_locks=4,
                  multi_instance=False, hold_time=0.003, seed=7):
    """Random workload for stress testing and benchmarks. Each task locks
    2..max_locks distinct resources in random order.

    multi_instance=True gives each resource 1-3 instances (matrix path)."""
    rng = random.Random(seed)
    res = {f"R{i}": (rng.randint(1, 3) if multi_instance else 1)
           for i in range(resources)}
    names = list(res)
    tasks = []
    for p in range(processes):
        k = rng.randint(2, min(max_locks, resources))
        chosen = rng.sample(names, k)   # distinct, in random order
        tasks.append(Task(f"P{p}", [Step(r, hold_time) for r in chosen],
                          priority=rng.randint(0, 9)))
    return res, tasks


SCENARIOS = {
    "bank": bank_transfers,
    "bank_ordered": lambda **kw: bank_transfers(ordered=True, **kw),
    "philosophers": dining_philosophers,
    "pool": connection_pool,
    "stress": random_stress,
    "stress_multi": lambda **kw: random_stress(multi_instance=True, **kw),
}
