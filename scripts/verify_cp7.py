"""Read-only acceptance checks for CP7 evidence, configuration and wiring."""
import ast
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import shutil

ROOT = Path(__file__).resolve().parents[1]
DEV = ROOT / "06-lab-complete/benchmark-observability/develop"
REPORTS = DEV / "reports"
EVIDENCE = ROOT / "reports/cp7"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def check(condition, message):
    if not condition:
        raise AssertionError(message)
    print("VERIFIED:", message)


def main():
    before = read(EVIDENCE / "manifest-baseline.json")
    after = read(EVIDENCE / "manifest-fixed.json")
    dataset = DEV / "eval/golden_dataset.jsonl"
    check(before["dataset_sha256"] == after["dataset_sha256"] == digest(dataset),
          "Golden dataset hash unchanged before/after runs")
    protected = ["06-lab-complete/check_production_ready.py",
                 str(dataset.relative_to(ROOT)),
                 str((DEV / "load_test.py").relative_to(ROOT)),
                 str((DEV / "eval/run_eval.py").relative_to(ROOT))]
    # Use the host Git for this Windows checkout, preserving its ownership
    # and line-ending configuration. No persistent Git settings are changed.
    git = shutil.which("git.exe") or shutil.which("git")
    result = subprocess.run([git, "diff", "--exit-code", "--", *protected],
                            cwd=ROOT, capture_output=True)
    if result.returncode:
        print(result.stdout.decode(errors="replace"))
        print(result.stderr.decode(errors="replace"))
    check(result.returncode == 0, "Grader, golden dataset, load/eval tools untouched")
    check(before["mock_llm_sha256"] != after["mock_llm_sha256"] == digest(DEV / "utils/mock_llm.py"),
          "Baseline used old KB and final used current updated KB")
    runs = {item["name"]: item for item in before["runs"] + after["runs"]}
    names = [f"load_v2_c{c}" for c in (1, 10, 50, 100)]
    names += [f"load_v2_slow_{r}" for r in ("0", "0.03", "0.1")]
    names += ["eval_v1", "eval_v2", "eval_v2_fixed"]
    text = (ROOT / "BENCHMARK_REPORT.md").read_text(encoding="utf-8")
    dataset_ids = {json.loads(line)["id"] for line in dataset.read_text().splitlines() if line.strip()}
    for name in names:
        source = REPORTS / f"{name}.json"
        check(digest(source) == runs[name]["report_sha256"] == digest(ROOT / "reports" / source.name),
              f"{name}: actual-run hash equals submitted copy")
        report = read(source)
        if name.startswith("load_"):
            check(report["total_requests"] == sum(report["status_codes"].values()) == 300,
                  f"{name}: 300 actual requests accounted for")
            check(report["target"] == "http://localhost:8002" and runs[name]["environment"]["AGENT_VERSION"] == "v2",
                  f"{name}: correct v2 agent and port")
            gate = report["latency_ms"]["p95"] <= 500 and report["error_rate"] <= 0.02
            check(report["slo"]["passed"] == gate and runs[name]["exit_code"] == (0 if gate else 1),
                  f"{name}: real gate and exit code agree")
            if "_slow_" in name:
                rate = name.split("_slow_")[1]
                check(report["concurrency"] == 20 and runs[name]["environment"]["MOCK_SLOW_RATE"] == rate,
                      f"{name}: controlled slow-rate at concurrency 20")
                label = "0.03 (mặc định)" if rate == "0.03" else rate
                row = f"| {label} | {report['latency_ms']['avg']} | {report['latency_ms']['p95']} | {report['latency_ms']['p99']} |"
            else:
                c = int(name.split("_c")[1])
                check(report["concurrency"] == c and runs[name]["environment"]["MOCK_SLOW_RATE"] == "0.03",
                      f"{name}: correct concurrency and default slow rate")
                row = (f"| {c} | {report['rps']} | {report['latency_ms']['p50']} | "
                       f"{report['latency_ms']['p95']} | {report['latency_ms']['p99']} | "
                       f"{report['error_rate'] * 100:.2f}% |")
            check(row in text, f"{name}: report table equals JSON")
        else:
            check(report["total"] == len(report["results"]) == 23 and report["errors"] == 0
                  and {r["id"] for r in report["results"]} == dataset_ids,
                  f"{name}: all 23 golden IDs evaluated without HTTP errors")
    original, fixed = read(REPORTS / "eval_v2.json"), read(REPORTS / "eval_v2_fixed.json")
    old_correct = {r["id"] for r in original["results"] if r["passed"]}
    new_correct = {r["id"] for r in fixed["results"] if r["passed"]}
    check(fixed["passed"] == 23 and fixed["accuracy"] == 1 and old_correct <= new_correct
          and fixed["quality_gate"] == {"min_accuracy": 1.0, "regressions": [], "passed": True},
          "Final v2 strict gate PASS, 23/23, no regression")
    ci = read(REPORTS / "eval_ci.json")
    workflow = (ROOT / ".github/workflows/eval.yml").read_text()
    check(ci["quality_gate"]["passed"] and runs["eval_ci"]["exit_code"] == 0
          and "--min-accuracy 0.85" in workflow and "--baseline reports/eval_v2_fixed.json" in workflow,
          "CI workflow exists and equivalent local gate passed; no GitHub run claimed")
    metrics = (EVIDENCE / "metrics.prom").read_text()
    tree = ast.parse((DEV / "app.py").read_text())
    ask = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "ask")
    check("QUESTION_LENGTH.observe(len(body.question))" in ast.unparse(ask.body[0])
          and "agent_question_length_chars_count 1.0" in metrics
          and "agent_question_length_chars_sum 40.0" in metrics,
          "Histogram wired before LLM and observed on live request")
    check('http_requests_total{method="GET",route="unmatched",status="404"} 2.0' in metrics,
          "Two unknown URLs aggregate under unmatched label")
    for port in (8001, 8002):
        with socket.socket() as sock:
            check(sock.connect_ex(("127.0.0.1", port)) != 0, f"Owned local agent stopped: {port}")
    print("PASSED: CP7 acceptance verified. CP8 remains out of scope.")


if __name__ == "__main__":
    main()
