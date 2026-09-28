"""
Live demo: the order/refund deadlock from the problem statement.

Run from the project root:
    python -m locksight.simulator.order_refund

order-svc locks inventory then wallet; refund-svc locks wallet then
inventory. They deadlock, LockSight detects it, aborts one, the victim
retries, and both requests complete.
"""

import threading
import time

from locksight.runtime.locksight import LockSight

START = time.time()


def log(event):
    t = f"{time.time() - START:6.3f}s"
    kind = event["type"]
    if kind == "acquire":
        print(f"{t}  {event['pid']:<11} acquired {event['resource']}")
    elif kind == "wait":
        print(f"{t}  {event['pid']:<11} WAITING for {event['resource']}")
    elif kind == "release":
        print(f"{t}  {event['pid']:<11} released {event['resource']}")
    elif kind == "abort":
        print(f"{t}  *** DEADLOCK among {event['group']} "
              f"(detected by {event['method']})")
        print(f"{t}  *** victim: {event['pid']}  (policy: {event['policy']}, "
              f"freed {event['released']})")
    elif kind == "retry":
        print(f"{t}  {event['pid']:<11} restarting (attempt {event['attempt']})")


def main():
    sight = LockSight(detection="periodic", interval=0.2,
                      policy="lowest_priority")
    sight.add_resource("inventory:42")
    sight.add_resource("wallet:7")
    sight.on_event(log)

    def order(attempt):
        with sight.lock("inventory:42"):
            time.sleep(0.1)           # simulated work
            with sight.lock("wallet:7"):
                time.sleep(0.05)

    def refund(attempt):
        with sight.lock("wallet:7"):
            time.sleep(0.1)
            with sight.lock("inventory:42"):
                time.sleep(0.05)

    print("Starting order-svc (priority 5) and refund-svc (priority 1)\n")
    with sight:
        threads = [
            threading.Thread(target=sight.run, args=("order-svc", order, 5)),
            threading.Thread(target=sight.run, args=("refund-svc", refund, 1)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    print(f"\nBoth requests completed. Stats: {sight.stats}")


if __name__ == "__main__":
    main()
