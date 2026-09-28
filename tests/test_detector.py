from locksight.core.graph import ResourceGraph
from locksight.core.detector import find_deadlocks, find_sccs


def setup(processes, resources):
    g = ResourceGraph()
    for p in processes:
        g.add_process(p)
    for r in resources:
        g.add_resource(r)
    return g


def acquire(g, pid, rid):
    g.request_resource(pid, rid)
    g.grant(pid, rid)


def test_no_deadlock_when_nobody_waits():
    g = setup(["P1", "P2"], ["R1", "R2"])
    acquire(g, "P1", "R1")
    acquire(g, "P2", "R2")
    assert find_deadlocks(g) == []


def test_no_deadlock_for_simple_waiting_chain():
    # P1 waits for P2, but P2 is not waiting: P2 will finish and release.
    g = setup(["P1", "P2"], ["R1"])
    acquire(g, "P2", "R1")
    g.request_resource("P1", "R1")
    assert find_deadlocks(g) == []


def test_order_refund_deadlock():
    # The real-world scenario from the problem statement.
    g = setup(["order-svc", "refund-svc"], ["inventory:42", "wallet:7"])
    acquire(g, "order-svc", "inventory:42")
    acquire(g, "refund-svc", "wallet:7")
    g.request_resource("order-svc", "wallet:7")
    g.request_resource("refund-svc", "inventory:42")
    assert find_deadlocks(g) == [{"order-svc", "refund-svc"}]


def test_three_process_cycle():
    # P1 -> P2 -> P3 -> P1
    g = setup(["P1", "P2", "P3"], ["R1", "R2", "R3"])
    acquire(g, "P1", "R1")
    acquire(g, "P2", "R2")
    acquire(g, "P3", "R3")
    g.request_resource("P1", "R2")
    g.request_resource("P2", "R3")
    g.request_resource("P3", "R1")
    assert find_deadlocks(g) == [{"P1", "P2", "P3"}]


def test_finds_two_independent_deadlocks():
    # Plain DFS would stop at the first one. Tarjan finds both.
    g = setup(["A", "B", "C", "D"], ["R1", "R2", "R3", "R4"])
    acquire(g, "A", "R1"); acquire(g, "B", "R2")
    g.request_resource("A", "R2"); g.request_resource("B", "R1")
    acquire(g, "C", "R3"); acquire(g, "D", "R4")
    g.request_resource("C", "R4"); g.request_resource("D", "R3")
    found = find_deadlocks(g)
    assert len(found) == 2
    assert {"A", "B"} in found and {"C", "D"} in found


def test_process_waiting_on_a_deadlock_is_not_in_the_cycle():
    # E waits for A, and A is stuck in a cycle with B.
    # E is blocked, but it is not part of the cycle: breaking the
    # cycle will unblock it, so recovery only needs to target {A, B}.
    g = setup(["A", "B", "E"], ["R1", "R2"])
    acquire(g, "A", "R1"); acquire(g, "B", "R2")
    g.request_resource("A", "R2"); g.request_resource("B", "R1")
    g.request_resource("E", "R1")
    assert find_deadlocks(g) == [{"A", "B"}]


def test_large_cycle_does_not_hit_recursion_limit():
    # 5000 processes in one big cycle: a recursive version would crash.
    n = 5000
    graph = {i: [(i + 1) % n] for i in range(n)}
    sccs = find_sccs(graph)
    assert len(sccs) == 1 and len(sccs[0]) == n
