# LockSight

**Deadlock detection and recovery for concurrent workers that share locks.**

Operating Systems mini project, Unit 4 (Deadlock): *Deadlock Detection and Recovery System*.

**Full project report:** [docs/REPORT.md](docs/REPORT.md): theory, design, implementation, benchmark results and testing.

## The problem

Modern backends protect shared data with application-level locks: a row in an
order table, a user's wallet, a connection from a database pool. Databases
detect deadlocks among their *own* locks, but nothing watches locks taken by
application code. When two workers lock the same resources in opposite
orders, for example

- `order-svc` locks `inventory:42`, then waits for `wallet:7`
- `refund-svc` locks `wallet:7`, then waits for `inventory:42`

both hang until a timeout fires. Timeouts are slow, can kill workers that were
never deadlocked, and hide the real cause.

LockSight records every lock request, grant and release in a live **Resource
Allocation Graph**, detects deadlocks as they form, and breaks each one by
aborting a single, carefully chosen victim, which then retries automatically.

## Features

- **Two detection algorithms, chosen automatically.** Tarjan's strongly
  connected components on the wait-for graph for single-instance resources
  (O(V+E), finds every deadlocked group in one pass), and the matrix detection
  algorithm for multi-instance resources such as connection pools, where a
  cycle alone does not prove deadlock.
- **Recovery with five victim-selection policies:** lowest priority, least
  work done, most resources held, and a combined weighted policy (plus its
  original un-normalised version for comparison). Starvation protection stops
  one task being chosen as victim forever.
- **Live threaded runtime.** Worker threads use `sight.lock(...)`. Victims are
  never killed: they are woken, raise `DeadlockVictimError`, unwind cleanly,
  and retry with random back-off to avoid livelock.
- **Two detection modes:** on every blocked request, or periodically in a
  background thread.
- **Workload simulator:** bank transfers, dining philosophers, a database
  connection pool, and random stress workloads, all reproducible from a seed.
- **Live dashboard** that draws the graph in real time, highlights each
  deadlock cycle and its victim, tracks the phase of each run, and narrates
  every step in plain English.
- **Interactive blueprint walkthrough**: ten numbered sheets explaining the
  theory, beside a 3D Resource Allocation Graph that redraws itself for each
  sheet (the order/refund cycle, Tarjan's deadlocked groups, a victim being
  removed, a fixed lock order, the dining philosophers). Drag to rotate it;
  each condition, policy and scenario opens a data sheet with a button to run
  it live.
- **Benchmark suite** that produces the charts and tables in the report.
- **71 automated tests**, including real multi-threaded deadlocks.

## Quick start

Requires Python 3.11 or newer.

```bash
git clone <your-repo-url> locksight
cd locksight
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q
```

### Watch a deadlock in the terminal

```bash
python -m locksight.simulator.order_refund
```

### Open the live dashboard

```bash
python -m locksight.server.app
```

Then open <http://localhost:8000>, choose a scenario and press
**Run scenario**. Stop the server with `Ctrl + C`.

### Run a scenario from the command line

```bash
python -m locksight.simulator.run bank
python -m locksight.simulator.run philosophers --detection on_block
python -m locksight.simulator.run pool --policy lowest_priority
```

Scenarios: `bank`, `bank_ordered`, `philosophers`, `pool`, `stress`,
`stress_multi`.

### Run the benchmarks

```bash
python -m benchmarks.run_benchmarks          # full run, about 3 minutes
python -m benchmarks.run_benchmarks --quick  # quick check, about 10 seconds
```

Charts, CSV files and `summary.md` are written to `benchmarks/results/`.

## Using LockSight in code

```python
from locksight.runtime.locksight import LockSight

sight = LockSight(detection="on_block", policy="weighted")
sight.add_resource("inventory:42")
sight.add_resource("wallet:7")
sight.add_resource("db-pool", instances=3)

def refund(attempt):
    with sight.lock("wallet:7"):
        with sight.lock("inventory:42"):
            ...  # do the work

with sight:
    sight.run("refund-svc", refund, priority=2)   # retried if chosen as victim
```

## Architecture

```
worker threads ──sight.lock()──► LockSight runtime
                                   │  records request / grant / release
                                   ▼
                              ResourceGraph  (allocation + request edges)
                                   │
                         detect()  │  Tarjan SCC  or  matrix algorithm
                                   ▼
                             RecoveryManager ── choose_victim() ── policies
                                   │  abort victim, release its resources
                                   ▼
                  events ──► FastAPI + WebSocket ──► browser dashboard
```

## Project structure

| Folder | Contents |
|---|---|
| `locksight/core/` | `graph.py` (Resource Allocation Graph with holder index), `detector.py` (Tarjan SCC), `matrix_detector.py` (multi-instance detection), `detect.py` (chooses the algorithm) |
| `locksight/recovery/` | `policies.py` (victim selection), `manager.py` (detect, abort, repeat) |
| `locksight/runtime/` | `locksight.py` (instrumented locks for real threads) |
| `locksight/simulator/` | `workload.py` (runner and metrics), `scenarios.py`, `run.py` (CLI), `order_refund.py` (terminal demo) |
| `locksight/server/` | `app.py` (FastAPI server streaming events over WebSocket) |
| `dashboard/` | `index.html` (page), `app.css` (styles), `sim.js` (simulation, tabs, modals), `story.js` (3D blueprint figure and scroll effects), `vendor/` (libraries, served locally) |
| `benchmarks/` | `run_benchmarks.py` and generated `results/` |
| `docs/` | `REPORT.md` (project report) and `images/` |
| `tests/` | pytest suite |

## Design decisions

- **One condition variable guards the graph**, so the detector always sees a
  consistent state. This serialises lock operations, which is the main
  scalability limit.
- **The graph keeps a reverse index** (`held_by`, `allocated`). Benchmarks
  showed that without it, building the wait-for graph was O(n²). With it,
  detection at 10,000 processes dropped from about 3 s to about 20 ms.
- **Recovery aborts one victim at a time** and re-runs detection, which wastes
  less work than aborting the whole cycle.
- **Every dashboard message carries a full graph snapshot**, so the browser can
  never drift out of sync with the server.

## Limitations and future scope

- Aborted work restarts from the beginning; rollback to checkpoints would
  waste less.
- Detection and recovery waste much more work than lock ordering under heavy
  contention; LockSight is for systems where a global lock order cannot be
  imposed.
- Workers are threads in one process; tracking locks across separate services
  over the network is the natural next step, along with handling phantom
  deadlocks caused by delayed events.
- The dashboard runs one scenario at a time.

## Dependencies and references

- [FastAPI](https://fastapi.tiangolo.com/) and [Uvicorn](https://www.uvicorn.org/): dashboard server
- [Cytoscape.js](https://js.cytoscape.org/) 3.34.3 (MIT licence): graph drawing, bundled in `dashboard/vendor/`
- [Three.js](https://threejs.org/) r170 (MIT licence): 3D blueprint figure, bundled in `dashboard/vendor/`
- [GSAP](https://gsap.com/) 3.12.5 with ScrollTrigger (GSAP standard licence): animations, bundled in `dashboard/vendor/`
- [Lenis](https://lenis.darkroom.engineering/) 1.1.13 (MIT licence): smooth scrolling, bundled in `dashboard/vendor/`
- [matplotlib](https://matplotlib.org/): benchmark charts
- [pytest](https://pytest.org/) and [HTTPX](https://www.python-httpx.org/): tests
- A. Silberschatz, P. B. Galvin, G. Gagne, *Operating System Concepts*, Wiley, chapter on deadlocks: detection algorithm and recovery strategies
- R. Tarjan, "Depth-first search and linear graph algorithms", *SIAM Journal on Computing*, 1(2), 1972
