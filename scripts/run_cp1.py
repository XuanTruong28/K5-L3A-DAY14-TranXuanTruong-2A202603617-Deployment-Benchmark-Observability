"""Run the unmodified Part 1 examples sequentially and save real HTTP evidence.

From the repo root in WSL:
  /home/twentysix/.venvs/k5-day14/bin/python scripts/run_cp1.py
"""
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "reports" / "cp1"


def curl(path, *, body=None, post=False):
    command = ["curl", "--silent", "--show-error", "--include", "--max-time", "5"]
    if post:
        command += ["-X", "POST"]
    if body is not None:
        command += ["-H", "Content-Type: application/json", "-d", json.dumps(body)]
    command += [f"http://127.0.0.1:8000{path}"]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    status = int(result.stdout.splitlines()[0].split()[1])
    return {"command": command, "status": status, "output": result.stdout}


def run(version, requests):
    # Refuse to record another process's responses as this exercise's evidence.
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", 8000)) == 0:
            raise RuntimeError("Port 8000 is occupied; stop the existing server first.")
    log_path = OUTPUT / f"{version}.log"
    env = dict(os.environ, DEBUG="false", HOST="0.0.0.0", PORT="8000",
               ENVIRONMENT="development", PYTHONUNBUFFERED="1")
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [sys.executable, "app.py"],
            cwd=ROOT / "01-localhost-vs-production" / version,
            env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
        )
        observations = []
        try:
            deadline = time.monotonic() + 45
            while True:
                if process.poll() is not None:
                    raise RuntimeError(f"{version} exited; inspect {log_path}")
                try:
                    with socket.create_connection(("127.0.0.1", 8000), timeout=0.5):
                        break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError(f"{version} did not start")
                    time.sleep(0.2)
            for path, options, expected in requests:
                observation = curl(path, **options)
                observations.append(observation)
                if observation["status"] != expected:
                    raise RuntimeError(f"Unexpected HTTP status: {observation}")
        finally:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                raise RuntimeError(f"{version} failed to stop within 15 seconds")
    # The develop example deliberately logs a fake key. Do not reproduce its value.
    log_text = log_path.read_text(encoding="utf-8")
    log_text = "\n".join(
        "[DEBUG] Using key: [REDACTED sample key]" if "[DEBUG] Using key:" in line else line
        for line in log_text.splitlines()
    ) + "\n"
    log_path.write_text(log_text, encoding="utf-8")
    return {
        "http": observations,
        "application_shutdown_complete_logged": "Application shutdown complete." in log_text,
        "custom_shutdown_message_logged": "Shutdown complete" in log_text,
    }


def main():
    if os.name != "posix":
        raise RuntimeError("Run this script from Ubuntu/WSL.")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    evidence = {"recorded_at_utc": datetime.now(timezone.utc).isoformat(),
                "python": sys.version, "os_name": os.name}
    evidence["develop"] = run("develop", [
        ("/ask?question=Hello", {"post": True}, 200),
        ("/ask", {"post": True, "body": {"question": "Hello"}}, 422),
        ("/health", {}, 404),
    ])
    evidence["production"] = run("production", [
        ("/ask", {"post": True, "body": {"question": "Hello"}}, 200),
        ("/ask", {"post": True, "body": {}}, 422),
        ("/health", {}, 200),
        ("/ready", {}, 200),
    ])
    if not evidence["production"]["application_shutdown_complete_logged"]:
        raise RuntimeError("Production did not log lifecycle shutdown completion.")
    (OUTPUT / "results.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for version in ("develop", "production"):
        print(version, [item["status"] for item in evidence[version]["http"]])
    print("Evidence saved to reports/cp1/results.json; both example servers stopped.")


if __name__ == "__main__":
    main()
