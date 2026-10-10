"""Fixed TeaStore WebUI journey derived from the repository's test_webui.sh."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = "/tools.descartes.teastore.webui"


def pick_ids(base: str) -> tuple[str, str]:
    for attempt in range(12):
        try:
            home = requests.get(base + ROOT + "/", timeout=20)
            category = re.search(r"category=(\d+)", home.text)
            if home.ok and category:
                cat = category.group(1)
                listing = requests.post(base + ROOT + "/category", params={"category": cat, "number": 30}, timeout=20)
                product = re.search(r"product\?id=(\d+)", listing.text)
                if listing.ok and product:
                    return cat, product.group(1)
        except requests.RequestException:
            pass
        if attempt != 11:
            time.sleep(5)
    raise RuntimeError("Could not discover a ready TeaStore category and product")


def run(base: str, repeats: int) -> dict:
    category, product = pick_ids(base)
    rows = []
    for run_id in range(1, repeats + 1):
        session = requests.Session()
        steps = [
            ("status", "GET", "/status", None),
            ("home", "GET", "/", None),
            ("login", "POST", "/loginAction?username=user2&password=password", None),
            ("category", "POST", f"/category?category={category}&number=30", None),
            ("product", "GET", f"/product?id={product}", None),
            ("add_cart", "POST", f"/cartAction?addToCart=&productid={product}", None),
            ("cart", "GET", "/cart", None),
        ]
        for step, method, path, data in steps:
            start = time.perf_counter()
            try:
                response = session.request(method, base + ROOT + path, data=data, timeout=30)
                row = {"run_id": run_id, "step": step, "method": method, "path": path,
                       "status": response.status_code, "latency_ms": round((time.perf_counter() - start) * 1000, 3),
                       "body_sha256": hashlib.sha256(response.content).hexdigest(), "body_bytes": len(response.content),
                       "status_ok_count": response.text.count("OK") if step == "status" else None,
                       "product_has_ads": ("Are you interested in" in response.text) if step == "product" else None,
                       "error": None}
            except requests.RequestException as exc:
                row = {"run_id": run_id, "step": step, "method": method, "path": path,
                       "status": None, "latency_ms": round((time.perf_counter() - start) * 1000, 3),
                       "body_sha256": None, "body_bytes": None, "status_ok_count": None,
                       "product_has_ads": None, "error": str(exc)}
            rows.append(row)
            time.sleep(0.2)
        session.close()
    return {"kind": "system_execution_gate_fixed_workload", "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "base_url": base, "repeats": repeats, "interval_s": 0.2, "category": category, "product": product, "rows": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18083")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.base_url, args.repeats)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"repeats": result["repeats"], "category": result["category"], "product": result["product"],
                      "statuses": [[r["step"], r["status"]] for r in result["rows"]],
                      "errors": sum(r["error"] is not None for r in result["rows"])}, ensure_ascii=False))
