"""Run the supplied CP7 tools against real local agents, saving raw evidence.

Run in WSL with the Part 6 Python environment, from the repo root:
  python scripts/run_cp7.py baseline
  # Review baseline failures, update KNOWLEDGE_BASE, then:
  python scripts/run_cp7.py fixed
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DEVELOP = ROOT / "06-lab-complete/benchmark-observability/develop"
REPORTS = DEVELOP / "reports"
EVIDENCE = ROOT / "reports/cp7"
DATASET = DEVELOP / "eval/golden_dataset.jsonl"
KB = DEVELOP / "utils/mock_llm.py"
BASE_CONFIG = {
    "LLM_MODEL": "mock-llm-small", "MOCK_LATENCY_MS": "120",
    "MOCK_JITTER_MS": "60", "MOCK_SLOW_MS": "1500",
    "MOCK_RETRIEVAL_MS": "20", "MOCK_SLOW_RATE": "0.03",
    "MOCK_ERROR_RATE": "0.01",
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fetch(port, path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        response = urllib.request.urlopen(request, timeout=10)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        return response.status, response.read().decode()


class Agent:
    def __init__(self, version, port, label, **overrides):
        self.port = port
        self.config = {**BASE_CONFIG, **overrides, "AGENT_VERSION": version, "PORT": str(port)}
        self.env = {**os.environ, **self.config, "PYTHONUNBUFFERED": "1"}
        self.env.pop("AGENT_API_KEY", None)
        self.process = None
        self.log = None
        self.label = label

    def __enter__(self):
        with socket.socket() as check:
            if check.connect_ex(("127.0.0.1", self.port)) == 0:
                raise RuntimeError(f"Port {self.port} occupied; refusing to stop another process")
        self.log = (EVIDENCE / f"{self.label}.log").open("w", encoding="utf-8")
        self.process = subprocess.Popen(
            [sys.executable, "app.py"], cwd=DEVELOP, env=self.env,
            stdout=self.log, stderr=subprocess.STDOUT, start_new_session=True,
        )
        try:
            for _ in range(150):
                if self.process.poll() is not None:
                    raise RuntimeError(f"Agent exited; inspect {self.label}.log")
                try:
                    status, body = fetch(self.port, "/health")
                    if status == 200 and json.loads(body)["agent_version"] == self.config["AGENT_VERSION"]:
                        return self
                except OSError:
                    pass
                time.sleep(0.1)
            raise RuntimeError("Agent startup timed out")
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_):
        if self.process is not None and self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait()
        if self.log is not None:
            self.log.close()


def run_tool(name, arguments, agent, manifest):
    output = REPORTS / f"{name}.json"
    if output.exists():
        raise RuntimeError(f"Refusing to overwrite existing evidence: {output}")
    command = [sys.executable, *arguments, "--url", f"http://localhost:{agent.port}",
               "--out", f"reports/{name}.json"]
    print(f"Running {name} ...", flush=True)
    started = datetime.now(timezone.utc).isoformat()
    result = subprocess.run(command, cwd=DEVELOP, env=agent.env, capture_output=True,
                            text=True, timeout=300)
    (EVIDENCE / f"{name}.txt").write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode not in (0, 1) or not output.exists():
        raise RuntimeError(f"{name} failed without valid report; inspect raw output")
    report = json.loads(output.read_text())
    if name.startswith("load_") and report["total_requests"] != 300:
        raise RuntimeError(f"{name} did not execute 300 requests")
    manifest["runs"].append({
        "name": name, "started_at_utc": started, "command": command,
        "environment": agent.config, "exit_code": result.returncode,
        "report_sha256": sha(output),
    })
    save(EVIDENCE / f"manifest-{manifest['phase']}.json", manifest)
    if name.startswith("load_"):
        print(f"  {report['total_requests']} requests; RPS={report['rps']}; "
              f"p95={report['latency_ms']['p95']}ms; SLO={report['slo']['passed']}", flush=True)
    else:
        print(f"  Eval {report['passed']}/{report['total']}; gate={report['quality_gate']['passed']}", flush=True)
    return report


def baseline(manifest):
    with Agent("v2", 8002, "v2-default") as agent:
        status, body = fetch(8002, "/ask", {"question": "Prometheus thu thập metrics như thế nào?"})
        if status != 200:
            raise RuntimeError("Example metrics request failed; rerun after reviewing raw log")
        save(EVIDENCE / "example-response.json", json.loads(body))
        for path in ("/cp7-unmatched-a", "/cp7-unmatched-b"):
            if fetch(8002, path)[0] != 404:
                raise RuntimeError("Expected unmatched route to return 404")
        status, metrics = fetch(8002, "/metrics")
        (EVIDENCE / "metrics.prom").write_text(metrics, encoding="utf-8")
        if status != 200 or "agent_question_length_chars_count 1.0" not in metrics:
            raise RuntimeError("Question-length Histogram was not observed")
        for concurrency in (1, 10, 50, 100):
            run_tool(f"load_v2_c{concurrency}", ["load_test.py", "--requests", "300",
                     "--concurrency", str(concurrency)], agent, manifest)
    for slow_rate in ("0", "0.03", "0.1"):
        with Agent("v2", 8002, f"v2-slow-{slow_rate}", MOCK_SLOW_RATE=slow_rate) as agent:
            run_tool(f"load_v2_slow_{slow_rate}", ["load_test.py", "--requests", "300",
                     "--concurrency", "20"], agent, manifest)
    # Disable random upstream errors for quality eval, as in the supplied CI example.
    with Agent("v1", 8001, "v1-eval", MOCK_ERROR_RATE="0") as agent:
        run_tool("eval_v1", ["eval/run_eval.py"], agent, manifest)
    with Agent("v2", 8002, "v2-eval-before", MOCK_ERROR_RATE="0") as agent:
        run_tool("eval_v2", ["eval/run_eval.py", "--baseline", "reports/eval_v1.json"], agent, manifest)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("baseline", "fixed"))
    args = parser.parse_args()
    if os.name != "posix":
        raise RuntimeError("Use the Linux Python environment in WSL")
    REPORTS.mkdir(parents=True, exist_ok=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    manifest_path = EVIDENCE / f"manifest-{args.phase}.json"
    if manifest_path.exists():
        raise RuntimeError("Existing manifest: inspect prior results before starting a new run")
    original_hash = sha(DATASET)
    manifest = {
        "phase": args.phase, "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version, "kernel": platform.release(),
        "linux": platform.freedesktop_os_release(), "cpu_count": os.cpu_count(),
        "memory_bytes": os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES"),
        "dataset_sha256": original_hash, "mock_llm_sha256": sha(KB), "runs": [],
    }
    save(manifest_path, manifest)
    if args.phase == "baseline":
        baseline(manifest)
    else:
        with Agent("v2", 8002, "v2-eval-fixed", MOCK_ERROR_RATE="0") as agent:
            report = run_tool("eval_v2_fixed", ["eval/run_eval.py", "--min-accuracy", "1.0",
                              "--baseline", "reports/eval_v2.json"], agent, manifest)
            if report["passed"] != 23 or not report["quality_gate"]["passed"]:
                raise RuntimeError("Final quality gate failed")
            ci_report = run_tool("eval_ci", ["eval/run_eval.py", "--min-accuracy", "0.85",
                                  "--baseline", "reports/eval_v2_fixed.json"], agent, manifest)
            if not ci_report["quality_gate"]["passed"]:
                raise RuntimeError("Local equivalent of the CI gate failed")
    if sha(DATASET) != original_hash:
        raise RuntimeError("Protected dataset changed during execution")
    manifest["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    save(manifest_path, manifest)
    print(f"CP7 {args.phase} complete; agent processes stopped.", flush=True)


if __name__ == "__main__":
    main()
