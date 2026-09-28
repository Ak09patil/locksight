"""
Dashboard server: runs scenarios and streams every lock event to the
browser over a WebSocket.

Start it from the project root:
    python -m locksight.server.app
Then open http://localhost:8000

How events travel (important for the viva):
  worker thread -> LockSight._emit() -> our listener -> Broadcaster.publish()
  -> asyncio queue of each connected browser -> WebSocket -> browser

The tricky part: LockSight listeners run on ordinary worker THREADS, but
FastAPI WebSockets live in an ASYNC event loop. Threads must not touch
asyncio objects directly, so publish() uses loop.call_soon_threadsafe(),
which hands the message to the event loop safely.

Each message carries a full snapshot of the graph, so the browser never has
to rebuild state from events and can't drift out of sync.
"""

import asyncio
import json
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from locksight.recovery.policies import POLICIES
from locksight.simulator.scenarios import (bank_transfers, connection_pool,
                                           dining_philosophers, random_stress)
from locksight.simulator.workload import run_workload

DASHBOARD_DIR = Path(__file__).resolve().parents[2] / "dashboard"

# Small, slowed-down versions of each scenario so a human can follow them.
DEMO_SCENARIOS = {
    "bank": lambda: bank_transfers(accounts=5, transfers=10, hold_time=0.25),
    "bank_ordered": lambda: bank_transfers(accounts=5, transfers=10,
                                           hold_time=0.25, ordered=True),
    "philosophers": lambda: dining_philosophers(n=5, rounds=1, hold_time=0.3),
    "pool": lambda: connection_pool(workers=4, pool_size=3, hold_time=0.3),
    "stress": lambda: random_stress(processes=8, resources=6, max_locks=3,
                                    hold_time=0.2),
    "stress_multi": lambda: random_stress(processes=8, resources=6,
                                          max_locks=3, multi_instance=True,
                                          hold_time=0.2),
}


class Broadcaster:
    """Fans messages out from worker threads to every connected browser."""

    def __init__(self):
        self.loop = None
        self._clients = set()
        self._lock = threading.Lock()

    def add(self, queue):
        with self._lock:
            self._clients.add(queue)

    def remove(self, queue):
        with self._lock:
            self._clients.discard(queue)

    def publish(self, message):
        """Safe to call from ANY thread."""
        if self.loop is None:
            return
        text = json.dumps(message, default=str)
        with self._lock:
            clients = list(self._clients)
        for queue in clients:
            try:
                self.loop.call_soon_threadsafe(queue.put_nowait, text)
            except RuntimeError:
                pass  # event loop already closed (server shutting down)


broadcaster = Broadcaster()
run_lock = threading.Lock()  # only one scenario runs at a time


@asynccontextmanager
async def lifespan(app):
    broadcaster.loop = asyncio.get_running_loop()
    yield
    broadcaster.loop = None


app = FastAPI(title="LockSight", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=DASHBOARD_DIR), name="static")


class RunRequest(BaseModel):
    scenario: str = "bank"
    detection: str = "periodic"
    policy: str = "weighted"
    interval: float = 0.3


@app.get("/")
def index():
    return FileResponse(DASHBOARD_DIR / "index.html")


@app.get("/api/options")
def options():
    return {"scenarios": list(DEMO_SCENARIOS),
            "detection": ["periodic", "on_block"],
            "policies": sorted(POLICIES)}


@app.post("/api/run")
def start_run(req: RunRequest):
    if req.scenario not in DEMO_SCENARIOS:
        raise HTTPException(400, f"Unknown scenario {req.scenario}")
    if req.detection not in ("periodic", "on_block"):
        raise HTTPException(400, f"Unknown detection mode {req.detection}")
    if req.policy not in POLICIES:
        raise HTTPException(400, f"Unknown policy {req.policy}")
    if not run_lock.acquire(blocking=False):
        raise HTTPException(409, "A run is already in progress")

    resources, tasks = DEMO_SCENARIOS[req.scenario]()
    threading.Thread(target=_run, args=(req, resources, tasks),
                     daemon=True).start()
    return {"status": "started", "tasks": len(tasks)}


def _run(req, resources, tasks):
    try:
        broadcaster.publish({
            "type": "run_start", "scenario": req.scenario,
            "detection": req.detection, "policy": req.policy,
            "resources": resources, "pids": [t.pid for t in tasks],
        })

        def attach(sight):
            def on_event(event):
                # snapshot() re-enters LockSight's lock, which is safe because
                # threading.Condition uses a re-entrant lock by default.
                broadcaster.publish({"type": "event", "event": event,
                                     "graph": sight.snapshot()})
            sight.on_event(on_event)

        result = run_workload(req.scenario, resources, tasks,
                              detection=req.detection, interval=req.interval,
                              policy=req.policy, setup=attach)
        broadcaster.publish({"type": "run_complete", "result": result.as_row()})
    except Exception as exc:
        broadcaster.publish({"type": "run_error", "error": str(exc)})
    finally:
        run_lock.release()


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    queue = asyncio.Queue()
    broadcaster.add(queue)
    try:
        while True:
            await ws.send_text(await queue.get())
    except WebSocketDisconnect:
        pass
    finally:
        broadcaster.remove(queue)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
