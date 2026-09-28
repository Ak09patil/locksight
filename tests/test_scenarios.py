"""
Scenario tests. Workloads are kept small so the suite stays fast.
"""

import pytest

from locksight.simulator.scenarios import (bank_transfers, connection_pool,
                                           dining_philosophers, random_stress)
from locksight.simulator.workload import run_workload


def check_all_completed(result):
    assert result.completed == result.tasks
    assert result.failed == 0


@pytest.mark.parametrize("mode", ["periodic", "on_block"])
def test_bank_transfers_complete(mode):
    res, tasks = bank_transfers(accounts=5, transfers=20)
    result = run_workload("bank", res, tasks, detection=mode, interval=0.02)
    check_all_completed(result)


def test_ordered_locking_never_deadlocks():
    # Prevention baseline: a global lock order removes circular wait,
    # so recovery should never be needed.
    res, tasks = bank_transfers(accounts=5, transfers=30, ordered=True)
    result = run_workload("bank_ordered", res, tasks, interval=0.02)
    check_all_completed(result)
    assert result.aborts == 0
    assert result.wasted_work == 0


def test_dining_philosophers_complete():
    res, tasks = dining_philosophers(n=5, rounds=2)
    result = run_workload("philosophers", res, tasks, detection="on_block")
    check_all_completed(result)


def test_connection_pool_completes():
    res, tasks = connection_pool(workers=4, pool_size=3)
    result = run_workload("pool", res, tasks, detection="on_block")
    check_all_completed(result)


def test_multi_instance_stress_completes():
    res, tasks = random_stress(processes=10, resources=6, multi_instance=True)
    result = run_workload("stress_multi", res, tasks, interval=0.02)
    check_all_completed(result)


def test_same_seed_gives_same_workload():
    a = random_stress(seed=3)
    b = random_stress(seed=3)
    c = random_stress(seed=4)
    assert a == b
    assert a != c


def test_metrics_are_consistent():
    res, tasks = bank_transfers(accounts=4, transfers=15)
    result = run_workload("bank", res, tasks, interval=0.02)
    row = result.as_row()
    assert row["tasks"] == 15
    assert result.throughput > 0
    assert result.detection_runs > 0
    assert (result.aborts == 0) == (result.wasted_work == 0)
