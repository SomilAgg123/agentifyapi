"""One-command demo, no Docker: start mock services, crawl, approve, serve, run the agent."""
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
PY = sys.executable
CFG = "examples/mcpify.yaml"
env = {**os.environ, "PYTHONPATH": f"{ROOT}:{ROOT / 'src'}", "MCPIFY_DESCRIBER": os.getenv("MCPIFY_DESCRIBER", "auto")}


def mcpify(*a):
    print("$ mcpify", " ".join(a), flush=True)
    subprocess.run([PY, "-m", "mcpify.cli", "-c", CFG, *a], check=True, env=env)


def wait(url):
    for _ in range(100):
        try:
            httpx.get(url, timeout=1)
            return
        except httpx.HTTPError:
            time.sleep(0.1)
    raise SystemExit(f"timed out waiting for {url}")


procs = []
try:
    Path("demo.db").unlink(missing_ok=True)
    for mod, port in (("orders", 8101), ("users", 8102)):
        procs.append(subprocess.Popen([PY, "-m", "uvicorn", f"examples.services.{mod}:app", "--port", str(port),
                                       "--log-level", "warning"], env=env))
        wait(f"http://127.0.0.1:{port}/openapi.json")
    mcpify("crawl")
    mcpify("tools", "list")
    mcpify("tools", "diff", "orders.get_order")
    for t in ("orders.get_order", "orders.list_orders", "users.get_user"):
        mcpify("tools", "approve", t, "--by", "demo-owner")
        mcpify("tools", "enable", t)
    procs.append(subprocess.Popen([PY, "-m", "mcpify.cli", "-c", CFG, "serve", "--port", "8000"], env=env))
    wait("http://127.0.0.1:8000/healthz")
    print("\nGateway: http://127.0.0.1:8000/mcp   Admin UI: http://127.0.0.1:8000/admin/\n")
    rc = subprocess.run([PY, "examples/agent_client.py"], env=env).returncode
    if "--keep" in sys.argv:
        print("\nRunning; Ctrl-C to stop.")
        procs[-1].wait()
    sys.exit(rc)
finally:
    for p in procs:
        p.terminate()
