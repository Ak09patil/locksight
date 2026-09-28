"""
Runtime tests with real threads.

Deadlocks are forced deterministically with a Barrier: both threads grab
their first lock, wait at the barrier until the other has too, and only
then request the second lock. Every thread is joined with a timeout, so a
bug makes the test FAIL instead of hanging forever.
"""

import threading

import pytest

from locksight.runtime.locksight import LockSight


def run_threads(targets, timeout=5):
    threads = [threading.Thread(target=t) for t in targets]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout)
    assert not any(t.is_alive() for t in threads), "a thread is stuck"


def order_refund_workers(sight, done, order_priority=0, refund_priority=0):
    barrier = threading.Barrier(2)

    def order(attempt):
        with sight.lock("inventory:42"):
            if attempt == 0:
                barrier.wait(timeout=2)
            with sight.lock("wallet:7"):
                done.append("order-svc")

    def refund(attempt):
        with sight.lock("wallet:7"):
            if attempt == 0:
                barrier.wait(timeout=2)
            with sight.lock("inventory:42"):
                done.append("refund-svc")

    return [lambda: sight.run("order-svc", order, priority=order_priority),
            lambda: sight.run("refund-svc", refund, priority=refund_priority)]


def make_sight(**kwargs):
    sight = LockSight(**kwargs)
    sight.add_resource("inventory:42")
    sight.add_resource("wallet:7")
    return sight


@pytest.mark.parametrize("mode", ["periodic", "on_block"])
def test_live_deadlock_is_resolved(mode):
    done = []
    with make_sight(detection=mode, interval=0.05) as sight:
        run_threads(order_refund_workers(sight, done))
    assert sorted(done) == ["order-svc", "refund-svc"]  # both finished
    assert sight.stats["aborts"] == 1
    assert sight.stats["retries"] == 1


def test_lowest_priority_thread_is_the_victim():
    done, aborted = [], []
    with make_sight(detection="on_block", policy="lowest_priority") as sight:
        sight.on_event(lambda e: e["type"] == "abort" and aborted.append(e["pid"]))
        run_threads(order_refund_workers(sight, done,
                                         order_priority=10, refund_priority=1))
    assert aborted == ["refund-svc"]


def test_connection_pool_deadlock_live():
    sight = LockSight(detection="on_block")
    sight.add_resource("db-pool", instances=2)
    barrier = threading.Barrier(2)
    done = []

    def worker(name):
        def body(attempt):
            with sight.lock("db-pool"):           # first connection
                if attempt == 0:
                    barrier.wait(timeout=2)
                with sight.lock("db-pool"):       # needs a second one
                    done.append(name)
        return lambda: sight.run(name, body)

    with sight:
        run_threads([worker("worker-1"), worker("worker-2")])
    assert sorted(done) == ["worker-1", "worker-2"]
    assert sight.stats["aborts"] == 1


def test_normal_contention_causes_no_aborts():
    # Many threads fighting over the same locks, but always in the SAME
    # order, so a deadlock is impossible. There must be zero false alarms.
    counter = {"n": 0}
    with make_sight(detection="on_block") as sight:
        def worker(i):
            def body(attempt):
                for _ in range(20):
                    with sight.lock("inventory:42"):
                        with sight.lock("wallet:7"):
                            counter["n"] += 1
            return lambda: sight.run(f"worker-{i}", body)
        run_threads([worker(i) for i in range(5)])
    assert counter["n"] == 100
    assert sight.stats["aborts"] == 0


def test_graph_is_empty_after_all_work_finishes():
    done = []
    with make_sight(detection="on_block") as sight:
        run_threads(order_refund_workers(sight, done))
    snap = sight.snapshot()
    assert snap["processes"] == []
    assert snap["allocation"] == {} and snap["request"] == {}


def test_lock_outside_process_is_rejected():
    sight = make_sight()
    with pytest.raises(RuntimeError):
        with sight.lock("wallet:7"):
            pass


def test_events_are_emitted():
    events = []
    with make_sight(detection="on_block") as sight:
        sight.on_event(lambda e: events.append(e["type"]))
        run_threads(order_refund_workers(sight, []))
    for expected in ["process_start", "acquire", "wait", "abort",
                     "retry", "release", "process_end"]:
        assert expected in events
