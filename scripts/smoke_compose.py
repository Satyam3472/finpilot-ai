"""Exercise a separate Docker project using synthetic data and temporary secrets."""

import argparse
import os
import secrets
import statistics
import subprocess
import tempfile
import time
from pathlib import Path

import httpx
from argon2 import PasswordHasher

from scripts.configure_local import create_secret

ROOT = Path(__file__).resolve().parents[1]


def smoke(port: int) -> None:
    project = "finpilot-smoke-" + secrets.token_hex(4)
    restored = project + "-restored"
    origin = f"http://127.0.0.1:{port}"
    password = secrets.token_urlsafe(24)
    print(f"Isolated Docker project: {project}", flush=True)
    with tempfile.TemporaryDirectory(prefix="finpilot-smoke-") as folder:
        for name, value in {
            "password_hash": PasswordHasher().hash(password),
            "session_secret": secrets.token_hex(32),
            "proxy_secret": secrets.token_hex(32),
            "gemini_key": "",
        }.items():
            create_secret(Path(folder), name, value)
        env = dict(os.environ, FINPILOT_SECRETS_DIR=folder, FINPILOT_REQUIRE_GEMINI="0",
                   FINPILOT_PORT=str(port), FINPILOT_ORIGIN=origin)

        def docker(*args, **options):
            return subprocess.run(["docker", *args], cwd=ROOT, env=env, check=True, **options)

        def compose(*args, **options):
            return docker("compose", "-p", project, *args, **options)

        try:
            compose("config", "--quiet")
            start = time.perf_counter()
            compose("up", "--build", "-d", "--wait", "--wait-timeout", "120")
            print(f"Build/start to all healthy: {time.perf_counter() - start:.2f}s", flush=True)
            compose("ps")
            compose("exec", "-T", "backend", "sh", "-ec",
                    "test \"$(id -u)\" = 10001; test ! -e /app/finance_agent/.env; test ! -e /app/.secrets")
            compose("exec", "-T", "frontend", "sh", "-ec",
                    "test \"$(id -u)\" != 0; test ! -e /app/.env.local; test ! -e /run/secrets/gemini_key")
            with httpx.Client(base_url=origin, headers={"Origin": origin}, timeout=10, trust_env=False) as client:
                assert client.get("/login").status_code == 200
                assert client.get("/api/health/ready").json() == {"status": "ready"}
                assert client.get("/api/transactions").status_code == 401
                login = client.post("/api/auth/login", json={"password": password})
                login.raise_for_status()
                assert "HttpOnly" in login.headers["set-cookie"]
                client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
                assert client.post("/api/chat/sessions", headers={"X-CSRF-Token": ""}).status_code == 403

                fixture = ROOT / "sample_data" / "analytics_statement.csv"
                start = time.perf_counter()
                response = client.post("/api/statements/upload", files={"file": (fixture.name, fixture.read_bytes())})
                response.raise_for_status()
                assert response.json()["imported_rows"] == 24
                print(f"24-row CSV import through proxy: {(time.perf_counter() - start) * 1000:.1f}ms", flush=True)

                timings = []
                for _ in range(8):
                    start = time.perf_counter()
                    summary = client.get("/api/dashboard/summary?month=2026-10").json()
                    assert summary["total_expenses_minor"] == 531_200
                    timings.append((time.perf_counter() - start) * 1000)
                print(f"Dashboard latency, 8 requests: median {statistics.median(timings):.1f}ms; max {max(timings):.1f}ms",
                      flush=True)
                allocation = client.put("/api/budgets/2026-10/food", json={"amount_minor": 200_000})
                assert allocation.json()["budgets"][0]["utilization_percent"] == 105.6
                session = client.post("/api/chat/sessions").json()["id"]
                reply = client.post(f"/api/chat/sessions/{session}/messages",
                                    json={"message": "Synthetic October 2026 expenses?"})
                assert reply.headers["content-type"].startswith("text/event-stream")
                assert "event: error" in reply.text and "event: done" not in reply.text
                assert "The assistant is unavailable" in reply.text
                print("Chat SSE traversed the proxy and returned a sanitized unavailable event without credentials.",
                      flush=True)

                def check_persistence():
                    assert client.get("/api/dashboard/summary?month=2026-10").json()["total_expenses_minor"] == 531_200
                    assert client.get("/api/budgets?month=2026-10").json()["budgets"][0]["budget_minor"] == 200_000
                    history = client.get(f"/api/chat/sessions/{session}").json()
                    assert history["id"] == session
                    assert {"role": "user", "text": "Synthetic October 2026 expenses?"} in history["messages"]

                start = time.perf_counter()
                compose("restart", "backend")
                compose("up", "-d", "--wait", "--wait-timeout", "90")
                print(f"Backend restart to healthy: {time.perf_counter() - start:.2f}s", flush=True)
                check_persistence()
                compose("down")
                compose("up", "-d", "--wait", "--wait-timeout", "90")
                check_persistence()

            compose("exec", "-T", "backend", "python", "-m", "scripts.backup_data", "--output", "/tmp/snapshot")
            tar = compose("exec", "-T", "backend", "tar", "-C", "/tmp/snapshot", "-cf", "-",
                          "transactions.sqlite3", "chat_sessions.sqlite3", stdout=subprocess.PIPE).stdout
            docker("run", "--rm", "-i", "--network", "none", "--cap-drop", "ALL",
                   "-v", f"{restored}:/data", f"{project}-backend", "sh", "-ec",
                   "umask 077; mkdir /tmp/snapshot; tar -xf - -C /tmp/snapshot; "
                   "python -m scripts.restore_data --source /tmp/snapshot --target /data --confirm; "
                   "python -c \"import sqlite3; assert sqlite3.connect('/data/transactions.sqlite3').execute('SELECT count(*) FROM transactions').fetchone()[0] == 24; assert sqlite3.connect('/data/chat_sessions.sqlite3').execute('SELECT count(*) FROM sessions').fetchone()[0] == 1\"",
                   input=tar)
            docker("image", "inspect", "--format", "{{.RepoTags}} {{.Size}} bytes",
                   f"{project}-backend", f"{project}-frontend")
            ids = compose("ps", "-q", capture_output=True, text=True).stdout.split()
            docker("stats", "--no-stream", "--format", "{{.Name}} {{.MemUsage}}", *ids)
            print("Smoke passed: authentication, proxy, import, budget, restart, recreation and separate-volume restore.", flush=True)
        finally:
            # Explicitly leave the isolated volumes available for diagnostic inspection.
            compose("down")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=3307)
    args = parser.parse_args()
    smoke(args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
