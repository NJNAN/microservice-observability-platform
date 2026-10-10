"""Capture current lab state and observed API contracts, without claiming improvements."""
import json
import subprocess
from pathlib import Path

import requests


def main():
    out = Path("data/validation")
    out.mkdir(parents=True, exist_ok=True)
    for name, url in {"api-topology": "http://localhost:8000/api/topology", "api-summary": "http://localhost:8000/api/traces/summary", "api-experiments": "http://localhost:8000/api/experiments"}.items():
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        (out / f"{name}.json").write_text(json.dumps(response.json(), indent=2), encoding="utf-8")
    query = 'count by(span_name) (traces_span_metrics_calls_total{span_kind="SPAN_KIND_SERVER"})'
    response = requests.get("http://localhost:9090/api/v1/query", params={"query": query}, timeout=30)
    response.raise_for_status()
    (out / "prometheus-operations.json").write_text(json.dumps(response.json(), indent=2), encoding="utf-8")
    print([r["metric"]["span_name"] for r in response.json()["data"]["result"]])
    for resource in ("pods", "deployments"):
        result = subprocess.check_output(["kubectl", "--context", "kind-mop", "-n", "mop", "get", resource, "-o", "json"], text=True)
        (out / f"{resource}.json").write_text(result, encoding="utf-8")
    summary = requests.get("http://localhost:8000/api/topology", timeout=30).json()
    graph = "flowchart LR\n" + "".join(f"  {e['source']} -->|{e['calls']} calls| {e['target']}\n" for e in summary["edges"])
    Path("docs/runtime-topology.mmd").write_text(graph, encoding="utf-8")


if __name__ == "__main__":
    main()
