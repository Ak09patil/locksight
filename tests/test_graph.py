import pytest
from locksight.core.graph import ResourceGraph, GraphError


def make_graph():
    g = ResourceGraph()
    for p in ["order-svc", "refund-svc"]:
        g.add_process(p)
    g.add_resource("inventory:42")
    g.add_resource("wallet:7")
    return g


def acquire(g, pid, rid, count=1):
    g.request_resource(pid, rid, count)
    g.grant(pid, rid, count)


def test_acquire_and_release():
    g = make_graph()
    acquire(g, "order-svc", "inventory:42")
    assert g.available("inventory:42") == 0
    assert g.holders("inventory:42") == {"order-svc"}
    g.release("order-svc", "inventory:42")
    assert g.available("inventory:42") == 1


def test_cannot_grant_unavailable_resource():
    g = make_graph()
    acquire(g, "order-svc", "wallet:7")
    g.request_resource("refund-svc", "wallet:7")
    with pytest.raises(GraphError):
        g.grant("refund-svc", "wallet:7")
    assert g.is_waiting("refund-svc")


def test_cannot_release_what_you_dont_hold():
    g = make_graph()
    with pytest.raises(GraphError):
        g.release("order-svc", "wallet:7")


def test_unknown_nodes_rejected():
    g = make_graph()
    with pytest.raises(GraphError):
        g.request_resource("ghost", "wallet:7")
    with pytest.raises(GraphError):
        g.request_resource("order-svc", "nothing")


def test_multi_instance_resource():
    g = make_graph()
    g.add_resource("db-conn-pool", instances=3)
    acquire(g, "order-svc", "db-conn-pool", 2)
    assert g.available("db-conn-pool") == 1
    with pytest.raises(GraphError):
        g.request_resource("refund-svc", "db-conn-pool", 4)  # more than exists


def test_wait_for_graph_order_refund_deadlock():
    # The real scenario: each service holds one lock and waits for the other's.
    g = make_graph()
    acquire(g, "order-svc", "inventory:42")
    acquire(g, "refund-svc", "wallet:7")
    g.request_resource("order-svc", "wallet:7")
    g.request_resource("refund-svc", "inventory:42")
    wfg = g.wait_for_graph()
    assert wfg["order-svc"] == {"refund-svc"}
    assert wfg["refund-svc"] == {"order-svc"}


def test_remove_process_frees_resources():
    g = make_graph()
    acquire(g, "order-svc", "inventory:42")
    g.remove_process("order-svc")
    assert g.available("inventory:42") == 1
    assert "order-svc" not in g.processes
