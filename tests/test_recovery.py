from locksight.core.graph import ResourceGraph
from locksight.core.detect import detect
from locksight.recovery.policies import ProcessMeta, choose_victim
from locksight.recovery.manager import RecoveryManager


def hold(g, pid, rid, n=1):
    g.request_resource(pid, rid, n)
    g.grant(pid, rid, n)


def order_refund_deadlock(extra_lock_for_order=False):
    g = ResourceGraph()
    g.add_process("order-svc"); g.add_process("refund-svc")
    g.add_resource("inventory:42"); g.add_resource("wallet:7")
    hold(g, "order-svc", "inventory:42")
    if extra_lock_for_order:
        g.add_resource("audit-log")
        hold(g, "order-svc", "audit-log")
    hold(g, "refund-svc", "wallet:7")
    g.request_resource("order-svc", "wallet:7")
    g.request_resource("refund-svc", "inventory:42")
    return g


def metas(**kwargs):
    table = {pid: ProcessMeta(**m) for pid, m in kwargs.items()}
    return lambda pid: table[pid]


GROUP = {"order-svc", "refund-svc"}


# ---------- individual policies ----------

def test_lowest_priority_policy():
    g = order_refund_deadlock()
    meta = lambda pid: {"order-svc": ProcessMeta(priority=10),
                        "refund-svc": ProcessMeta(priority=2)}[pid]
    assert choose_victim(g, GROUP, meta, "lowest_priority") == "refund-svc"


def test_least_work_policy():
    g = order_refund_deadlock()
    meta = lambda pid: {"order-svc": ProcessMeta(work_done=0.5),
                        "refund-svc": ProcessMeta(work_done=9.0)}[pid]
    assert choose_victim(g, GROUP, meta, "least_work") == "order-svc"


def test_most_resources_policy():
    g = order_refund_deadlock(extra_lock_for_order=True)  # order holds 2
    meta = lambda pid: ProcessMeta()
    assert choose_victim(g, GROUP, meta, "most_resources") == "order-svc"


def test_tie_break_is_deterministic():
    g = order_refund_deadlock()
    meta = lambda pid: ProcessMeta()
    first = choose_victim(g, GROUP, meta, "weighted")
    for _ in range(20):
        assert choose_victim(g, GROUP, meta, "weighted") == first


# ---------- starvation ----------

def test_starvation_protection_skips_repeat_victim():
    g = order_refund_deadlock()
    table = {"order-svc": ProcessMeta(priority=10),
             "refund-svc": ProcessMeta(priority=1, victim_count=3)}
    # refund-svc is cheapest, but it has already been aborted 3 times
    victim = choose_victim(g, GROUP, lambda p: table[p],
                           "lowest_priority", max_victim_count=3)
    assert victim == "order-svc"


def test_starvation_fallback_when_everyone_hit_limit():
    g = order_refund_deadlock()
    table = {"order-svc": ProcessMeta(priority=10, victim_count=3),
             "refund-svc": ProcessMeta(priority=1, victim_count=3)}
    victim = choose_victim(g, GROUP, lambda p: table[p],
                           "lowest_priority", max_victim_count=3)
    assert victim == "refund-svc"  # someone must still be chosen


def test_victim_count_survives_restart():
    # A process aborted, restarted with the same id, and deadlocked again
    # keeps its history, so it eventually gets protected.
    mgr = RecoveryManager(policy="lowest_priority", max_victim_count=2)
    mgr.set_meta("order-svc", priority=10)
    mgr.set_meta("refund-svc", priority=1)
    victims = []
    for _ in range(3):
        g = order_refund_deadlock()   # same deadlock happens again
        victims.append(mgr.recover(g)[0].victim)
    assert victims == ["refund-svc", "refund-svc", "order-svc"]


# ---------- full recovery ----------

def test_recover_clears_deadlock_and_records_action():
    g = order_refund_deadlock()
    mgr = RecoveryManager(policy="lowest_priority")
    mgr.set_meta("order-svc", priority=5)
    mgr.set_meta("refund-svc", priority=1)
    actions = mgr.recover(g)
    assert len(actions) == 1
    assert actions[0].victim == "refund-svc"
    assert actions[0].released == {"wallet:7": 1}
    assert actions[0].method == "tarjan"
    assert not detect(g).has_deadlock
    # order-svc's pending request can now be granted
    g.grant("order-svc", "wallet:7")


def test_one_abort_is_enough_for_three_process_cycle():
    g = ResourceGraph()
    for p in ["P1", "P2", "P3"]:
        g.add_process(p)
    for r in ["R1", "R2", "R3"]:
        g.add_resource(r)
    hold(g, "P1", "R1"); hold(g, "P2", "R2"); hold(g, "P3", "R3")
    g.request_resource("P1", "R2")
    g.request_resource("P2", "R3")
    g.request_resource("P3", "R1")
    actions = RecoveryManager().recover(g)
    assert len(actions) == 1           # not all three aborted
    assert len(g.processes) == 2


def test_recover_multiple_independent_deadlocks():
    g = ResourceGraph()
    for p in ["A", "B", "C", "D"]:
        g.add_process(p)
    for r in ["R1", "R2", "R3", "R4"]:
        g.add_resource(r)
    hold(g, "A", "R1"); hold(g, "B", "R2")
    g.request_resource("A", "R2"); g.request_resource("B", "R1")
    hold(g, "C", "R3"); hold(g, "D", "R4")
    g.request_resource("C", "R4"); g.request_resource("D", "R3")
    actions = RecoveryManager().recover(g)
    assert len(actions) == 2
    assert not detect(g).has_deadlock


def test_recover_connection_pool_deadlock():
    g = ResourceGraph()
    g.add_process("worker-1"); g.add_process("worker-2")
    g.add_resource("db-pool", 2)
    hold(g, "worker-1", "db-pool"); hold(g, "worker-2", "db-pool")
    g.request_resource("worker-1", "db-pool")
    g.request_resource("worker-2", "db-pool")
    actions = RecoveryManager().recover(g)
    assert len(actions) == 1
    assert actions[0].method == "matrix"
    assert not detect(g).has_deadlock


def test_no_action_when_no_deadlock():
    g = ResourceGraph()
    g.add_process("A"); g.add_resource("R1")
    hold(g, "A", "R1")
    assert RecoveryManager().recover(g) == []
