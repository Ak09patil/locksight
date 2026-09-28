"""
Tests for the normalised weighted policy vs the original weighted_raw.
"""

import pytest

from locksight.core.graph import ResourceGraph
from locksight.recovery.policies import (ProcessMeta, choose_victim,
                                         weighted_costs)


def three_way_deadlock():
    g = ResourceGraph()
    for p in ["A", "B", "C"]:
        g.add_process(p)
    for r in ["R1", "R2", "R3"]:
        g.add_resource(r)
    for p, r in [("A", "R1"), ("B", "R2"), ("C", "R3")]:
        g.request_resource(p, r)
        g.grant(p, r)
    g.request_resource("A", "R2")
    g.request_resource("B", "R3")
    g.request_resource("C", "R1")
    return g


# A has the lowest priority but has done 90x more work than B.
TABLE = {"A": ProcessMeta(priority=3, work_done=0.90),
         "B": ProcessMeta(priority=4, work_done=0.01),
         "C": ProcessMeta(priority=9, work_done=0.50)}
GROUP = {"A", "B", "C"}


def test_raw_policy_is_dominated_by_priority():
    # 3 + 0.90 < 4 + 0.01, so raw picks A and throws away 0.9 s of work.
    g = three_way_deadlock()
    assert choose_victim(g, GROUP, TABLE.get, "weighted_raw") == "A"


def test_normalised_policy_balances_priority_and_work():
    # After normalising, B's slightly higher priority no longer outweighs
    # A's much larger amount of work, so B (almost no work lost) is chosen.
    g = three_way_deadlock()
    assert choose_victim(g, GROUP, TABLE.get, "weighted") == "B"


def test_normalised_costs_are_in_a_bounded_range():
    g = three_way_deadlock()
    costs = weighted_costs(g, GROUP, TABLE.get)
    # Each of the 4 factors is in 0..1, one of them subtracted.
    assert all(-1.0 <= c <= 3.0 for c in costs.values())


def test_identical_candidates_do_not_divide_by_zero():
    g = three_way_deadlock()
    same = lambda p: ProcessMeta(priority=5, work_done=0.2)  # noqa: E731
    costs = weighted_costs(g, GROUP, same)
    assert set(costs.values()) == {0.0}


def test_unknown_policy_rejected():
    g = three_way_deadlock()
    with pytest.raises(ValueError):
        choose_victim(g, GROUP, TABLE.get, "nope")
