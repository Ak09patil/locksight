"""
Command-line runner for scenarios.

Examples (from the project root):
    python -m locksight.simulator.run bank
    python -m locksight.simulator.run bank_ordered
    python -m locksight.simulator.run philosophers --detection on_block
    python -m locksight.simulator.run pool --policy lowest_priority
    python -m locksight.simulator.run stress --interval 0.02
"""

import argparse

from locksight.recovery.policies import POLICIES
from locksight.simulator.scenarios import SCENARIOS
from locksight.simulator.workload import print_result, run_workload


def main():
    parser = argparse.ArgumentParser(description="Run a LockSight scenario")
    parser.add_argument("scenario", choices=sorted(SCENARIOS))
    parser.add_argument("--detection", choices=["periodic", "on_block"],
                        default="periodic")
    parser.add_argument("--interval", type=float, default=0.05,
                        help="seconds between periodic detection runs")
    parser.add_argument("--policy", choices=sorted(POLICIES), default="weighted")
    args = parser.parse_args()

    resources, tasks = SCENARIOS[args.scenario]()
    print(f"Running '{args.scenario}': {len(tasks)} tasks, "
          f"{len(resources)} resources, detection={args.detection}, "
          f"policy={args.policy}")
    result = run_workload(args.scenario, resources, tasks,
                          detection=args.detection, interval=args.interval,
                          policy=args.policy)
    print_result(result)


if __name__ == "__main__":
    main()
