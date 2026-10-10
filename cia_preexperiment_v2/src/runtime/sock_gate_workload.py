"""Fixed Sock Shop read journey, including deterministic missing-item probes."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

PATHS = [
    "/",
    "/catalogue",
    "/catalogue/03fef6ac-1896-4ce8-bd69-b798f85c6e0b",
    "/catalogue/size",
    "/tags",
    "/customers",
    "/carts/1",  # A stable 404 still exercises the carts request path.
    "/orders/1",  # A stable 404 still exercises the orders request path.
]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18081")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    rows = []
    for run_id in range(1, args.repeats + 1):
        session = requests.Session()
        for path in PATHS:
            start = time.perf_counter()
            try:
                response = session.get(args.base_url + path, timeout=20)
                row = {"run_id": run_id, "path": path, "status": response.status_code,
                       "latency_ms": round((time.perf_counter() - start) * 1000, 3),
                       "body_sha256": hashlib.sha256(response.content).hexdigest(), "error": None}
            except requests.RequestException as exc:
                row = {"run_id": run_id, "path": path, "status": None,
                       "latency_ms": round((time.perf_counter() - start) * 1000, 3),
                       "body_sha256": None, "error": str(exc)}
            rows.append(row)
            time.sleep(0.2)
        session.close()
    payload = {"kind": "system_execution_gate_fixed_workload", "timestamp_utc": datetime.now(timezone.utc).isoformat(),
               "base_url": args.base_url, "repeats": args.repeats, "interval_s": 0.2, "rows": rows}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"runs": args.repeats, "status_by_path": {path: [r["status"] for r in rows if r["path"] == path] for path in PATHS},
                      "errors": sum(r["error"] is not None for r in rows)}))
