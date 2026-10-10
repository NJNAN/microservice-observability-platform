"""Collect three independent fixed-workload repetitions and functional oracles."""

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))
from gate_workload import CHECKOUT, PRODUCT, execute
from online_boutique_trace_gate import audit, fetch_traces


def http_oracle():
    base = "http://127.0.0.1:18080"
    session = requests.Session()
    result = {}
    home = session.get(base + "/", timeout=30)
    soup = BeautifulSoup(home.text, "html.parser")
    result["frontend.GET_home"] = {
        "status": home.status_code,
        "products": [(name.get_text(strip=True), price.get_text(strip=True))
                     for name, price in zip(soup.select(".hot-product-card-name"), soup.select(".hot-product-card-price"))],
        "currencies": [option.get("value") for option in soup.select("#currency_form option")],
    }
    product = session.get(base + f"/product/{PRODUCT}", timeout=30)
    soup = BeautifulSoup(product.text, "html.parser")
    price = soup.select_one(".product-price")
    result["frontend.GET_product"] = {"status": product.status_code, "price": price.get_text(strip=True) if price else None}
    session.post(base + "/cart", data={"product_id": PRODUCT, "quantity": "1"}, timeout=30)
    cart = session.get(base + "/cart", timeout=30)
    soup = BeautifulSoup(cart.text, "html.parser")
    rows = [soup.select_one(selector) for selector in (".cart-summary-shipping-row", ".cart-summary-total-row")]
    result["frontend.GET_cart"] = {
        "status": cart.status_code,
        "shipping": re.findall(r"\$\d+\.\d+", rows[0].get_text(" ", strip=True)) if rows[0] else [],
        "total": re.findall(r"\$\d+\.\d+", rows[1].get_text(" ", strip=True)) if rows[1] else [],
    }
    checkout = session.post(base + "/cart/checkout", data=CHECKOUT, timeout=30)
    soup = BeautifulSoup(checkout.text, "html.parser")
    checkout_text = soup.get_text(" ", strip=True)
    match = re.search(r"Total Paid\s*(\$\d+\.\d+)", checkout_text)
    result["frontend.POST_checkout"] = {"status": checkout.status_code, "total": match.group(1) if match else None}
    session.close()
    return result


def grpc_oracle():
    proc = subprocess.run(
        ["docker", "exec", "cia-online-boutique-v2-recommendationservice-1", "python", "/tmp/oracle_probe.py"],
        text=True, capture_output=True, check=True, timeout=60,
    )
    return json.loads(proc.stdout)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["original", "changed"], required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for index in range(1, 4):
        # Oracles themselves call services. Keep those calls outside the next
        # repetition's pre-change trace window.
        time.sleep(3)
        start_us = int(time.time() * 1_000_000) - 1_000_000
        workload = execute("http://127.0.0.1:18080", repeats=1, interval_s=0.2)
        end_us = int(time.time() * 1_000_000) + 2_000_000
        time.sleep(8)
        traces = fetch_traces("http://127.0.0.1:16686", start_us, end_us)
        trace_summary = audit(traces)
        oracle = {"grpc": grpc_oracle(), "http": http_oracle()}
        prefix = args.out_dir / f"{args.phase}_{index:02d}"
        prefix.with_suffix(".workload.json").write_text(json.dumps(workload, indent=2), encoding="utf-8")
        prefix.with_suffix(".traces.json").write_text(json.dumps({"data": traces}, indent=2), encoding="utf-8")
        prefix.with_suffix(".trace_summary.json").write_text(json.dumps(trace_summary, indent=2), encoding="utf-8")
        prefix.with_suffix(".oracle.json").write_text(json.dumps(oracle, indent=2), encoding="utf-8")
        print(json.dumps({
            "phase": args.phase, "rep": index,
            "workload_statuses": [row["status"] for row in workload["rows"]],
            "traces": trace_summary["trace_count"],
            "spans": trace_summary["span_count"],
            "edges": trace_summary["unique_cross_service_directed_edges"],
            "oracle_product_price": oracle["http"]["frontend.GET_product"],
            "oracle_currency": oracle["grpc"]["CurrencyService.Convert.USD_USD"],
        }), flush=True)


if __name__ == "__main__":
    main()
