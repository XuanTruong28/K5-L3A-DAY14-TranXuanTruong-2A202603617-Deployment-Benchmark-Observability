"""Observe real Prometheus alert transitions; never synthesize firing times.

Time to firing is first observed firing minus the recorded config-apply start.
Polling uncertainty is up to five seconds, excluding API/network latency.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "reports/cp8"


def utc_now():
    return datetime.now(timezone.utc)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", required=True, choices=("A", "B"))
    parser.add_argument("--alert", action="append", required=True)
    args = parser.parse_args()
    started = datetime.fromisoformat(
        (EVIDENCE / f"alert-{args.phase}-start.txt").read_text().strip().replace("Z", "+00:00")
    )
    output = EVIDENCE / f"alert-{args.phase}-observation.json"
    if output.exists():
        raise SystemExit(f"Evidence already exists: {output}; preserve it before a new run")
    record = {
        "phase": args.phase, "config_apply_start_utc": started.isoformat(),
        "required_alerts": args.alert, "poll_interval_seconds": 5,
        "timing_definition": "first observed firing minus config apply start; not exact transition time",
        "first_firing": {}, "samples": [],
    }
    previous = None
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen("http://localhost:9090/api/v1/alerts", timeout=10) as response:
                payload = json.load(response)
            if payload.get("status") != "success":
                raise ValueError("Prometheus API did not return success")
            now = utc_now()
            alerts = payload["data"]["alerts"]
            relevant = [alert for alert in alerts if alert["labels"].get("alertname") in args.alert]
            states = {name: "inactive" for name in args.alert}
            for alert in relevant:
                name = alert["labels"]["alertname"]
                states[name] = alert["state"]
                if alert["state"] == "firing" and name not in record["first_firing"]:
                    record["first_firing"][name] = {
                        "observed_at_utc": now.isoformat(),
                        "seconds_since_config_apply": round((now - started).total_seconds(), 1),
                        "alert": alert,
                    }
            record["samples"].append({"observed_at_utc": now.isoformat(), "states": states, "alerts": alerts})
            output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            if states != previous:
                print(now.isoformat(), states, flush=True)
                previous = states
            if all(states[name] == "firing" for name in args.alert):
                record["all_required_firing_observed_at_utc"] = now.isoformat()
                output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                for name in args.alert:
                    print(name, "first observed firing after",
                          record["first_firing"][name]["seconds_since_config_apply"], "seconds", flush=True)
                print(f"Evidence saved: {output}", flush=True)
                return
        except (OSError, ValueError, KeyError) as exc:
            print(f"Waiting for Prometheus: {type(exc).__name__}: {exc}", flush=True)
        time.sleep(5)
    raise SystemExit("Timeout: required alerts were not all observed firing; inspect evidence, do not invent times")


if __name__ == "__main__":
    main()
