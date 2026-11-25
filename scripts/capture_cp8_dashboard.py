"""Capture exact dashboard queries during a new, explicitly labelled CP8 run."""
import datetime
import json
import pathlib
import subprocess
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROD = ROOT / "06-lab-complete/benchmark-observability/production"
OUT = ROOT / "reports/cp8/dashboard-exact"
COMPOSE = ["docker", "compose", "-p", "k5-day14-observability"]


def run(*args):
    return subprocess.check_output(COMPOSE + list(args), cwd=PROD, text=True,
                                   encoding="utf-8", errors="replace")


def query(expr, timestamp):
    params = urllib.parse.urlencode({"query": expr, "time": timestamp})
    with urllib.request.urlopen("http://localhost:9090/api/v1/query?" + params,
                                timeout=15) as response:
        result = json.load(response)
    if result["status"] != "success" or not result["data"]["result"]:
        raise RuntimeError("Prometheus query returned no evidence")
    return result


def main():
    OUT.mkdir(exist_ok=False)
    try:
        deadline = time.monotonic() + 90
        while True:
            status = run("ps", "--format", "json", "agent")
            agents = [json.loads(line) for line in status.splitlines() if line.strip()]
            if len(agents) == 2 and all(a.get("Health") == "healthy" for a in agents):
                break
            if time.monotonic() > deadline:
                raise RuntimeError("Two healthy agents not available")
            time.sleep(3)
        (OUT / "agent-status-before.jsonl").write_text(status, encoding="utf-8")
        command = COMPOSE + ["run", "--rm", "--no-deps", "locust", "-f",
                             "/mnt/locust/locustfile.py", "--host", "http://nginx",
                             "--headless", "-u", "30", "-r", "5", "-t", "2m"]
        started = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with (OUT / "locust.txt").open("w", encoding="utf-8") as logfile:
            process = subprocess.Popen(command, cwd=PROD, stdout=logfile,
                                       stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 100
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError("Locust exited before capture")
                    time.sleep(2)
                timestamp = time.time()
                dashboard = json.loads((PROD / "grafana/dashboards/agent-overview.json").read_text(encoding="utf-8"))
                titles = {"Latency /ask — p50 / p95 / p99", "Requests/s theo instance", "Tokens/s", "Instances up"}
                results = []
                for panel in dashboard["panels"]:
                    if panel.get("title") not in titles:
                        continue
                    for target in panel.get("targets", []):
                        results.append({"panel": panel["title"], "legend": target.get("legendFormat"),
                                        "query": target["expr"], "response": query(target["expr"], timestamp)})
                record = {"started_utc": started, "captured_unix": timestamp,
                          "captured_utc": datetime.datetime.fromtimestamp(timestamp, datetime.timezone.utc).isoformat(),
                          "workload": "NEW run; 2 agents, 30 users, ramp-up 5/s, 2 minutes; capture at ~100s",
                          "command": command, "results": results}
                (OUT / "prometheus.json").write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
                exit_code = process.wait(timeout=45)
                (OUT / "exit-code.txt").write_text(str(exit_code) + "\n", encoding="utf-8")
                (OUT / "agent-status-after.jsonl").write_text(run("ps", "--format", "json", "agent"), encoding="utf-8")
                print("Captured exact dashboard queries:", OUT / "prometheus.json", flush=True)
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=15)
    finally:
        with (OUT / "cleanup.txt").open("w", encoding="utf-8") as logfile:
            subprocess.run(COMPOSE + ["down", "-v"], cwd=PROD, stdout=logfile,
                           stderr=subprocess.STDOUT, check=True)
        (OUT / "after-cleanup.txt").write_text(run("ps", "-a"), encoding="utf-8")


if __name__ == "__main__":
    main()
