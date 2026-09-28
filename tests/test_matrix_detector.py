from locksight.core.graph import ResourceGraph
from locksight.core.detector import find_deadlocks
from locksight.core.matrix_detector import find_deadlocked_processes
from locksight.core.detect import detect


def hold(g, pid, rid, n=1):
    g.request_resource(pid, rid, n)
    g.grant(pid, rid, n)


def textbook_graph():
    """Silberschatz example: 5 processes, A=7, B=2, C=6 instances.
    Allocation: P0 (0,1,0) P1 (2,0,0) P2 (3,0,3) P3 (2,1,1) P4 (0,0,2)
    Request:    P0 (0,0,0) P1 (2,0,2) P2 (0,0,0) P3 (1,0,0) P4 (0,0,2)
    Available afterwards: (0,0,0)
    """
    g = ResourceGraph()
    for p in ["P0", "P1", "P2", "P3", "P4"]:
        g.add_process(p)
    g.add_resource("A", 7)
    g.add_resource("B", 2)
    g.add_resource("C", 6)

    hold(g, "P0", "B", 1)
    hold(g, "P1", "A", 2)
    hold(g, "P2", "A", 3); hold(g, "P2", "C", 3)
    hold(g, "P3", "A", 2); hold(g, "P3", "B", 1); hold(g, "P3", "C", 1)
    hold(g, "P4", "C", 2)

    g.request_resource("P1", "A", 2); g.request_resource("P1", "C", 2)
    g.request_resource("P3", "A", 1)
    g.request_resource("P4", "C", 2)
    return g


def test_textbook_example_is_safe():
    g = textbook_graph()
    assert find_deadlocked_processes(g) == set()


def test_textbook_example_deadlocks_after_extra_request():
    # Textbook follow-up: P2 asks for one more C. Now only P0 can finish,
    # and releasing its one B does not help anyone else.
    g = textbook_graph()
    g.request_resource("P2", "C", 1)
    assert find_deadlocked_processes(g) == {"P1", "P2", "P3", "P4"}


def test_cycle_without_deadlock():
    # The key case that shows WHY this algorithm is needed.
    # R1 has 2 instances. P1 and P3 each hold one. P2 holds R2.
    # P1 waits for R2, P2 waits for R1  ->  cycle P1 <-> P2.
    # But P3 is not waiting: it will finish and free an R1 instance.
    g = ResourceGraph()
    for p in ["P1", "P2", "P3"]:
        g.add_process(p)
    g.add_resource("R1", 2)
    g.add_resource("R2", 1)
    hold(g, "P1", "R1"); hold(g, "P3", "R1"); hold(g, "P2", "R2")
    g.request_resource("P1", "R2")
    g.request_resource("P2", "R1")

    assert find_deadlocks(g) != []                  # Tarjan: false alarm
    assert find_deadlocked_processes(g) == set()    # Matrix: correct


def test_connection_pool_deadlock():
    # Real scenario: a pool of 2 DB connections. Two workers each grab one
    # and then each need a second one to run a transaction.
    g = ResourceGraph()
    g.add_process("worker-1"); g.add_process("worker-2")
    g.add_resource("db-pool", 2)
    hold(g, "worker-1", "db-pool"); hold(g, "worker-2", "db-pool")
    g.request_resource("worker-1", "db-pool")
    g.request_resource("worker-2", "db-pool")
    result = detect(g)
    assert result.method == "matrix"
    assert result.deadlocks == [{"worker-1", "worker-2"}]


def test_detect_picks_tarjan_for_single_instance():
    g = ResourceGraph()
    g.add_process("A"); g.add_process("B")
    g.add_resource("R1"); g.add_resource("R2")
    hold(g, "A", "R1"); hold(g, "B", "R2")
    g.request_resource("A", "R2"); g.request_resource("B", "R1")
    result = detect(g)
    assert result.method == "tarjan"
    assert result.has_deadlock
    assert result.deadlocks == [{"A", "B"}]


def test_matrix_groups_independent_deadlocks():
    g = ResourceGraph()
    for p in ["A", "B", "C", "D"]:
        g.add_process(p)
    g.add_resource("pool1", 2)
    g.add_resource("pool2", 2)
    hold(g, "A", "pool1"); hold(g, "B", "pool1")
    g.request_resource("A", "pool1"); g.request_resource("B", "pool1")
    hold(g, "C", "pool2"); hold(g, "D", "pool2")
    g.request_resource("C", "pool2"); g.request_resource("D", "pool2")
    result = detect(g)
    assert len(result.deadlocks) == 2
    assert {"A", "B"} in result.deadlocks and {"C", "D"} in result.deadlocks


def test_no_deadlock_result():
    g = ResourceGraph()
    g.add_process("A")
    g.add_resource("pool", 3)
    hold(g, "A", "pool", 2)
    result = detect(g)
    assert not result.has_deadlock
