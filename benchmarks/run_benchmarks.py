"""
LockSight benchmark suite. Produces the tables and graphs for the report's
Results & Discussion section.

Run from the project root:
    python -m benchmarks.run_benchmarks            # full run (a few minutes)
    python -m benchmarks.run_benchmarks --quick    # fast smoke run

Output goes to benchmarks/results/:
    *.csv        raw numbers (one row per measurement)
    *.png        charts for the report and PPT
    summary.md   markdown tables, ready to paste into the report

Experiments:
  1. Detection scaling      Tarjan vs matrix algorithm as the graph grows
  2. Detection modes        on-block vs periodic (3 intervals) on real workloads
  3. Victim policies        aborts, wasted work, fairness per policy
  4. Prevention vs recovery lock ordering vs detection + recovery

Threaded experiments are repeated and averaged, because thread timing
varies between runs. Workloads use fixed seeds, so every configuration
sees exactly the same tasks.
"""

import argparse
import csv
import random
import statistics
import time
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # draw to files, no window needed
import matplotlib.pyplot as plt  # noqa: E402

from locksight.core.detector import find_deadlocks  # noqa: E402
from locksight.core.graph import ResourceGraph  # noqa: E402
from locksight.core.matrix_detector import find_deadlocked_processes  # noqa: E402
from locksight.simulator.scenarios import (bank_transfers,  # noqa: E402
                                           dining_philosophers, random_stress)
from locksight.simulator.workload import run_workload  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"

COLORS = ["#1e3a5f", "#0f766e", "#d97706", "#dc2626", "#7c3aed", "#64748b"]
plt.rcParams.update({"figure.dpi": 150, "font.size": 10,
                     "axes.spines.top": False, "axes.spines.right": False})


# ---------------------------------------------------------------- helpers

def write_csv(name, rows):
    path = RESULTS / f"{name}.csv"
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def mean(values):
    return statistics.mean(values) if values else 0.0


def md_table(rows, columns):
    head = "| " + " | ".join(columns) + " |"
    sep = "|" + "|".join("---" for _ in columns) + "|"
    body = ["| " + " | ".join(str(r[c]) for c in columns) + " |" for r in rows]
    return "\n".join([head, sep, *body])


def log(msg):
    print(msg, flush=True)


# ------------------------------------------------ 1. detection scaling

def synthetic_graph(n, wait_prob=0.7, seed=0):
    """n processes and n single-instance resources. Process i holds R_i and,
    with probability wait_prob, waits for another random resource. Random
    waits create a mix of chains and cycles, like a busy real system."""
    rng = random.Random(seed)
    g = ResourceGraph()
    for i in range(n):
        g.add_process(f"P{i}")
        g.add_resource(f"R{i}")
        g.request_resource(f"P{i}", f"R{i}")
        g.grant(f"P{i}", f"R{i}")
    for i in range(n):
        if rng.random() < wait_prob:
            j = rng.randrange(n)
            if j != i:
                g.request_resource(f"P{i}", f"R{j}")
    return g


def chain_graph(n):
    """Worst case for the matrix algorithm: a chain P0 -> P1 -> ... -> Pn-1,
    where Pi holds Ri and waits for R(i+1). Only the LAST process can finish
    first, and the algorithm scans processes from P0, so each full pass frees
    just one process: n passes of n checks = O(n^2). No deadlock exists."""
    g = ResourceGraph()
    for i in range(n):
        g.add_process(f"P{i}")
        g.add_resource(f"R{i}")
        g.request_resource(f"P{i}", f"R{i}")
        g.grant(f"P{i}", f"R{i}")
    for i in range(n - 1):
        g.request_resource(f"P{i}", f"R{i + 1}")
    return g


def time_call(fn, repeats):
    best = float("inf")
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - t0)
    return best


def exp_detection_scaling(quick):
    log("1/4  Detection scaling")
    sizes = [10, 50, 100, 250] if quick else [10, 50, 100, 250, 500, 1000,
                                               2000, 5000, 10000]
    repeats = 2 if quick else 5
    matrix_budget = 5.0   # stop timing the matrix algorithm once it is slow
    rows = []

    for kind, make in [("random", synthetic_graph),
                       ("worst-case chain", chain_graph)]:
        matrix_on = True
        for n in sizes:
            g = make(n)
            t_tarjan = time_call(lambda: find_deadlocks(g), repeats)
            row = {"graph": kind, "processes": n,
                   "tarjan_ms": round(t_tarjan * 1000, 3), "matrix_ms": "",
                   "tarjan_deadlocked": sum(len(x) for x in find_deadlocks(g)),
                   "matrix_deadlocked": ""}
            if matrix_on:
                t_matrix = time_call(lambda: find_deadlocked_processes(g), 1)
                row["matrix_ms"] = round(t_matrix * 1000, 3)
                row["matrix_deadlocked"] = len(find_deadlocked_processes(g))
                if t_matrix > matrix_budget:
                    matrix_on = False
            rows.append(row)
            log(f"     {kind:<17} n={n:<6} tarjan={row['tarjan_ms']} ms  "
                f"matrix={row['matrix_ms'] or 'skipped (too slow)'} ms")

    write_csv("detection_scaling", rows)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4), sharey=True)
    for ax, kind in zip(axes, ["random", "worst-case chain"]):
        rs = [r for r in rows if r["graph"] == kind]
        ax.plot([r["processes"] for r in rs], [r["tarjan_ms"] for r in rs],
                "o-", color=COLORS[1], label="Tarjan SCC  O(V+E)")
        ms = [r for r in rs if r["matrix_ms"] != ""]
        ax.plot([r["processes"] for r in ms], [r["matrix_ms"] for r in ms],
                "s-", color=COLORS[3], label="Matrix algorithm  O(m·n²)")
        baseline = RESULTS / "detection_scaling_baseline.csv"
        if kind == "random" and baseline.exists():
            # Measured before the holder index was added to ResourceGraph.
            with open(baseline) as f:
                base = [r for r in csv.DictReader(f)
                        if r.get("graph", "random") == "random"]
            ax.plot([int(r["processes"]) for r in base],
                    [float(r["tarjan_ms"]) for r in base], "o--",
                    color="#94a3b8", label="Tarjan, before holder index")
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("Processes in the graph (log scale)")
        ax.set_title(f"{kind.capitalize()} graphs")
        ax.grid(True, which="major", alpha=0.3)
        ax.legend(frameon=False, fontsize=8)
    axes[0].set_ylabel("Detection time, ms (log scale)")
    fig.suptitle("Detection time as the graph grows")
    fig.tight_layout()
    fig.savefig(RESULTS / "detection_scaling.png")
    plt.close(fig)
    return rows


# ------------------------------------------------ 2. detection modes

def workload_set(quick):
    """Full-speed workloads used by experiments 2 and 3."""
    if quick:
        return {
            "bank": lambda: bank_transfers(accounts=6, transfers=20),
            "philosophers": lambda: dining_philosophers(n=5, rounds=2),
        }
    return {
        "bank": lambda: bank_transfers(accounts=10, transfers=60),
        "philosophers": lambda: dining_philosophers(n=8, rounds=3),
        "stress": lambda: random_stress(processes=20, resources=10,
                                        max_locks=3),
    }


def exp_detection_modes(quick):
    log("2/4  Detection modes")
    modes = [("on_block", None), ("periodic", 0.01), ("periodic", 0.05),
             ("periodic", 0.2)]
    repeats = 1 if quick else 3
    rows = []
    for scen, make in workload_set(quick).items():
        for mode, interval in modes:
            label = "on-block" if mode == "on_block" else f"periodic {int(interval * 1000)} ms"
            runs = []
            for _ in range(repeats):
                res, tasks = make()
                runs.append(run_workload(scen, res, tasks, detection=mode,
                                         interval=interval or 0.05))
            row = {
                "scenario": scen, "mode": label,
                "wall_time_s": round(mean([r.wall_time for r in runs]), 3),
                "throughput_per_s": round(mean([r.throughput for r in runs]), 1),
                "aborts": round(mean([r.aborts for r in runs]), 1),
                "detection_runs": round(mean([r.detection_runs for r in runs]), 1),
                "detection_time_ms": round(mean([r.detection_time for r in runs]) * 1000, 2),
                "failed": sum(r.failed for r in runs),
            }
            rows.append(row)
            log(f"     {scen:<13} {label:<15} throughput={row['throughput_per_s']:>6}/s "
                f"runs={row['detection_runs']}")
    write_csv("detection_modes", rows)

    scenarios = list(dict.fromkeys(r["scenario"] for r in rows))
    labels = list(dict.fromkeys(r["mode"] for r in rows))
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    width = 0.8 / len(labels)
    for k, (metric, title) in enumerate([
            ("throughput_per_s", "Throughput (tasks/s, higher is better)"),
            ("detection_runs", "Detection runs (lower = less overhead)")]):
        ax = axes[k]
        for i, lab in enumerate(labels):
            vals = [next(r[metric] for r in rows
                         if r["scenario"] == s and r["mode"] == lab)
                    for s in scenarios]
            xs = [x + i * width - 0.4 + width / 2 for x in range(len(scenarios))]
            ax.bar(xs, vals, width, label=lab, color=COLORS[i])
        ax.set_xticks(range(len(scenarios)))
        ax.set_xticklabels(scenarios)
        ax.set_title(title)
    axes[0].legend(frameon=False, fontsize=8)
    fig.suptitle("On-block vs periodic detection")
    fig.tight_layout()
    fig.savefig(RESULTS / "detection_modes.png")
    plt.close(fig)
    return rows


# ------------------------------------------------ 3. victim policies

POLICY_ORDER = ["lowest_priority", "least_work", "most_resources",
                "weighted_raw", "weighted"]


def exp_policies(quick):
    log("3/4  Victim policies")
    repeats = 2 if quick else 5
    rows = []
    for scen, make in workload_set(quick).items():
        for policy in POLICY_ORDER:
            runs, max_aborts, victim_prios, all_prios = [], [], [], []
            for _ in range(repeats):
                res, tasks = make()
                prio = {t.pid: t.priority for t in tasks}
                all_prios.extend(prio.values())
                per_pid = Counter()

                def setup(sight, per_pid=per_pid):
                    def on_event(e):
                        if e["type"] == "abort":
                            per_pid[e["pid"]] += 1
                    sight.on_event(on_event)

                runs.append(run_workload(scen, res, tasks, detection="on_block",
                                         policy=policy, setup=setup))
                max_aborts.append(max(per_pid.values(), default=0))
                victim_prios.extend(prio[p] for p, n in per_pid.items()
                                    for _ in range(n))
            row = {
                "scenario": scen, "policy": policy,
                "aborts": round(mean([r.aborts for r in runs]), 1),
                "wasted_work_s": round(mean([r.wasted_work for r in runs]), 3),
                "throughput_per_s": round(mean([r.throughput for r in runs]), 1),
                "max_aborts_one_task": round(mean(max_aborts), 1),
                "avg_victim_priority": round(mean(victim_prios), 2) if victim_prios else "",
                "avg_task_priority": round(mean(all_prios), 2),
                "failed": sum(r.failed for r in runs),
            }
            rows.append(row)
            log(f"     {scen:<13} {policy:<16} aborts={row['aborts']:>5} "
                f"wasted={row['wasted_work_s']:>6}s")
    write_csv("policies", rows)

    scenarios = list(dict.fromkeys(r["scenario"] for r in rows))
    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    width = 0.8 / len(POLICY_ORDER)
    for k, (metric, title) in enumerate([
            ("wasted_work_s", "Wasted work, s (lower is better)"),
            ("aborts", "Aborts (lower is better)"),
            ("max_aborts_one_task", "Most aborts of one task (fairness)")]):
        ax = axes[k]
        for i, pol in enumerate(POLICY_ORDER):
            vals = [next(r[metric] for r in rows
                         if r["scenario"] == s and r["policy"] == pol)
                    for s in scenarios]
            xs = [x + i * width - 0.4 + width / 2 for x in range(len(scenarios))]
            ax.bar(xs, vals, width, label=pol.replace("_", " "), color=COLORS[i])
        ax.set_xticks(range(len(scenarios)))
        ax.set_xticklabels(scenarios)
        ax.set_title(title)
    axes[0].legend(frameon=False, fontsize=8)
    fig.suptitle("Victim selection policies (on-block detection)")
    fig.tight_layout()
    fig.savefig(RESULTS / "policies.png")
    plt.close(fig)
    return rows


# ------------------------------------------------ 4. prevention vs recovery

def exp_prevention(quick):
    log("4/4  Prevention vs detection + recovery")
    sizes = [20, 40] if quick else [20, 40, 80, 160]
    repeats = 1 if quick else 3
    rows = []
    for n in sizes:
        for ordered, label in [(False, "detection + recovery"),
                               (True, "prevention (lock ordering)")]:
            runs = []
            for _ in range(repeats):
                res, tasks = bank_transfers(accounts=10, transfers=n,
                                            ordered=ordered)
                runs.append(run_workload("bank", res, tasks,
                                         detection="on_block"))
            row = {"transfers": n, "approach": label,
                   "wall_time_s": round(mean([r.wall_time for r in runs]), 3),
                   "throughput_per_s": round(mean([r.throughput for r in runs]), 1),
                   "aborts": round(mean([r.aborts for r in runs]), 1),
                   "wasted_work_s": round(mean([r.wasted_work for r in runs]), 3)}
            rows.append(row)
            log(f"     transfers={n:<4} {label:<27} "
                f"throughput={row['throughput_per_s']}/s aborts={row['aborts']}")
    write_csv("prevention_vs_recovery", rows)

    fig, ax = plt.subplots(figsize=(6.4, 4))
    for i, label in enumerate(["detection + recovery",
                               "prevention (lock ordering)"]):
        rs = [r for r in rows if r["approach"] == label]
        ax.plot([r["transfers"] for r in rs], [r["throughput_per_s"] for r in rs],
                "o-", color=COLORS[3 if i == 0 else 1], label=label)
    ax.set_xlabel("Concurrent bank transfers")
    ax.set_ylabel("Throughput (tasks/s)")
    ax.set_title("Prevention vs detection + recovery")
    ax.legend(frameon=False)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(RESULTS / "prevention_vs_recovery.png")
    plt.close(fig)
    return rows


# ------------------------------------------------ main

def main(argv=None):
    parser = argparse.ArgumentParser(description="Run LockSight benchmarks")
    parser.add_argument("--quick", action="store_true",
                        help="small, fast run (for checking everything works)")
    parser.add_argument("--only", choices=["scaling", "modes", "policies",
                                           "prevention"],
                        help="run just one experiment")
    args = parser.parse_args(argv)

    RESULTS.mkdir(parents=True, exist_ok=True)
    started = time.time()
    sections = []

    if args.only in (None, "scaling"):
        rows = exp_detection_scaling(args.quick)
        sections.append("## 1. Detection time vs graph size\n\n" + md_table(
            rows, ["graph", "processes", "tarjan_ms", "matrix_ms", "tarjan_deadlocked",
                   "matrix_deadlocked"]))
    if args.only in (None, "modes"):
        rows = exp_detection_modes(args.quick)
        sections.append("## 2. On-block vs periodic detection\n\n" + md_table(
            rows, ["scenario", "mode", "throughput_per_s", "wall_time_s",
                   "aborts", "detection_runs", "detection_time_ms"]))
    if args.only in (None, "policies"):
        rows = exp_policies(args.quick)
        sections.append("## 3. Victim selection policies\n\n" + md_table(
            rows, ["scenario", "policy", "aborts", "wasted_work_s",
                   "throughput_per_s", "max_aborts_one_task",
                   "avg_victim_priority", "avg_task_priority"]))
    if args.only in (None, "prevention"):
        rows = exp_prevention(args.quick)
        sections.append("## 4. Prevention vs detection + recovery\n\n" + md_table(
            rows, ["transfers", "approach", "throughput_per_s", "wall_time_s",
                   "aborts", "wasted_work_s"]))

    header = (f"# LockSight benchmark results\n\n"
              f"Mode: {'quick' if args.quick else 'full'}. "
              f"Generated {time.strftime('%Y-%m-%d %H:%M')}, "
              f"took {time.time() - started:.0f} s.\n")
    (RESULTS / "summary.md").write_text(header + "\n\n".join([""] + sections) + "\n")
    log(f"\nDone in {time.time() - started:.0f} s. Results in {RESULTS}")


if __name__ == "__main__":
    main()
