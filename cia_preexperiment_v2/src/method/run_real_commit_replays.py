"""Execute historically sourced commit deltas with fixed tracing runtime."""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CASES = json.loads((ROOT / "data/commits/method_replays/cases.json").read_text(encoding="utf-8"))
BASE = ROOT / "configs/online_boutique_trace_gate.compose.yml"
RESULTS = ROOT / "results/raw/method_real_replays"
COLLECTOR = Path(__file__).with_name("collect_pilot_phase.py")
PROBE = Path(__file__).with_name("oracle_probe.py")
CONTAINER = "cia-online-boutique-v2-recommendationservice-1"


def command(parts, timeout=240):
    result = subprocess.run(parts, text=True, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"{parts}: {result.stdout}\n{result.stderr}")
    return result.stdout


def set_version(case, phase):
    parts = ["docker", "compose", "-f", str(BASE)]
    override = case.get("override_" + phase)
    if override:
        parts += ["-f", override]
    command(parts + ["up", "-d", "--no-deps", "--force-recreate", case["changed_service"]])
    time.sleep(5)
    service = case["changed_service"]
    state = command(["docker", "inspect", "--format", "{{.State.Running}}", f"cia-online-boutique-v2-{service}-1"]).strip()
    if state != "true":
        raise RuntimeError(f"{service} not running in {phase} version")
    if service == "recommendationservice":
        command(["docker", "cp", str(PROBE), f"{CONTAINER}:/tmp/oracle_probe.py"])


def run_case(case):
    case_id = case["case_id"]
    out = RESULTS / case_id
    out.mkdir(parents=True, exist_ok=True)
    progress = {"case_id": case_id, "commit": case["commit"], "status": "started", "phases": []}
    progress_path = out / "progress.json"
    progress_path.write_text(json.dumps(progress, indent=2), encoding="utf-8")
    try:
        if case.get("build_context"):
            print(f"BUILD {case_id}", flush=True)
            command(["docker", "build", "-t", case["original_image"], case["build_context"]], timeout=900)
        for phase in ("original", "changed"):
            set_version(case, phase)
            output = command([sys.executable, str(COLLECTOR), "--phase", phase, "--out-dir", str(out)], timeout=240)
            print(output, end="", flush=True)
            progress["phases"].append(phase)
            progress_path.write_text(json.dumps(progress, indent=2), encoding="utf-8")
        progress["status"] = "complete"
    except Exception as exc:
        progress["status"] = "error"
        progress["error"] = str(exc)
        print(f"CASE ERROR {case_id}: {exc}", flush=True)
    finally:
        try:
            command(["docker", "compose", "-f", str(BASE), "up", "-d", "--no-deps", "--force-recreate", case["changed_service"]])
        except Exception as exc:
            progress["restore_error"] = str(exc)
        progress_path.write_text(json.dumps(progress, indent=2), encoding="utf-8")
    return progress


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", action="append")
    parser.add_argument("--skip-complete", action="store_true")
    args = parser.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)
    chosen = [case for case in CASES if not args.case or case["case_id"] in args.case]
    if args.skip_complete:
        chosen = [case for case in chosen if not (
            (RESULTS / case["case_id"] / "progress.json").exists()
            and json.loads((RESULTS / case["case_id"] / "progress.json").read_text(encoding="utf-8"))["status"] == "complete"
        )]
    command(["docker", "cp", str(PROBE), f"{CONTAINER}:/tmp/oracle_probe.py"])
    results = []
    for index, case in enumerate(chosen, 1):
        print(f"REAL CASE {index}/{len(chosen)} {case['case_id']}", flush=True)
        results.append(run_case(case))
    all_progress = []
    for case in CASES:
        path = RESULTS / case["case_id"] / "progress.json"
        all_progress.append(json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"case_id": case["case_id"], "status": "not_run"})
    summary = {"total": len(CASES), "complete": sum(x["status"] == "complete" for x in all_progress), "errors": [x for x in all_progress if x["status"] != "complete"]}
    (RESULTS / "run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    return 0 if not summary["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
