"""
The holder index (held_by, allocated) must always agree with allocation.
This test performs thousands of random operations and, after each one,
recomputes the answer the slow way and compares.
"""

import random

import pytest

from locksight.core.graph import GraphError, ResourceGraph


def slow_holders(g, rid):
    return {p for p, a in g.allocation.items() if a.get(rid, 0) > 0}


def slow_available(g, rid):
    return g.resources[rid] - sum(a.get(rid, 0) for a in g.allocation.values())


@pytest.mark.parametrize("seed", range(5))
def test_index_matches_allocation_after_random_operations(seed):
    rng = random.Random(seed)
    g = ResourceGraph()
    pids = [f"P{i}" for i in range(8)]
    rids = [f"R{i}" for i in range(5)]
    for p in pids:
        g.add_process(p)
    for r in rids:
        g.add_resource(r, rng.randint(1, 3))

    for _ in range(3000):
        op = rng.choice(["acquire", "acquire", "release", "remove"])
        p, r = rng.choice(pids), rng.choice(rids)
        try:
            if op == "acquire":
                g.request_resource(p, r)
                if g.available(r) >= 1:
                    g.grant(p, r)
                else:
                    g.request[p][r] -= 1          # give up waiting
                    if g.request[p][r] == 0:
                        del g.request[p][r]
            elif op == "release":
                g.release(p, r)
            else:
                g.remove_process(p)
                g.add_process(p)                  # restart it
        except GraphError:
            pass  # invalid random operation, graph must be unchanged

        for rid in rids:
            assert g.holders(rid) == slow_holders(g, rid)
            assert g.available(rid) == slow_available(g, rid)
            assert 0 <= g.available(rid) <= g.resources[rid]
