"""Fixed, repeatable Online Boutique journeys for the execution gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

PRODUCT = "OLJCESPC7Z"
CHECKOUT = {
    "email": "cia-gate@example.test",
    "street_address": "1 Experiment Way",
    "zip_code": "94043",
    "city": "Mountain View",
    "state": "CA",
    "country": "United States",
    "credit_card_number": "4111111111111111",
    "credit_card_expiration_month": "12",
    "credit_card_expiration_year": "2030",
    "credit_card_cvv": "123",
}


def execute(base_url: str, repeats: int, interval_s: float) -> dict:
    rows = []
    for run_id in range(1, repeats + 1):
        session = requests.Session()
        steps = [
            ("home", "GET", "/", None),
            ("product", "GET", f"/product/{PRODUCT}", None),
            ("add_cart", "POST", "/cart", {"product_id": PRODUCT, "quantity": "1"}),
            ("view_cart", "GET", "/cart", None),
            ("checkout", "POST", "/cart/checkout", CHECKOUT),
        ]
        for step, method, path, form in steps:
            start = time.perf_counter()
            try:
                response = session.request(method, base_url + path, data=form, timeout=30)
                record = {
                    "run_id": run_id,
                    "step": step,
                    "method": method,
                    "path": path,
                    "status": response.status_code,
                    "latency_ms": round((time.perf_counter() - start) * 1000, 3),
                    "body_sha256": hashlib.sha256(response.content).hexdigest(),
                    "body_bytes": len(response.content),
                    "error": None,
                }
            except requests.RequestException as exc:
                record = {
                    "run_id": run_id,
                    "step": step,
                    "method": method,
                    "path": path,
                    "status": None,
                    "latency_ms": round((time.perf_counter() - start) * 1000, 3),
                    "body_sha256": None,
                    "body_bytes": None,
                    "error": str(exc),
                }
            rows.append(record)
            time.sleep(interval_s)
        session.close()
    return {
        "kind": "system_execution_gate_fixed_workload",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "seed": 42,
        "repeats": repeats,
        "interval_s": interval_s,
        "rows": rows,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18080")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--interval-s", type=float, default=0.2)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    outcome = execute(args.base_url, args.repeats, args.interval_s)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(outcome, indent=2), encoding="utf-8")
    print(json.dumps({"statuses": [[r["step"], r["status"]] for r in outcome["rows"]], "errors": sum(r["error"] is not None for r in outcome["rows"])}))
