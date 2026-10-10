"""Live UI/API/metrics contract smoke test; requires manage.py ports and demo."""
import json
import time
from pathlib import Path

import requests


def get(url, **params):
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def main():
    result = {"timestamp": time.time(), "checks": {}}
    assert get("http://127.0.0.1:8000/health")["status"] == "ok"
    summary = get("http://127.0.0.1:8000/api/traces/summary")
    assert len(summary["observed_services"]) == 10
    assert summary["unique_cross_service_directed_edges"] >= 14
    result["checks"]["api"] = {"services": 10, "edges": summary["unique_cross_service_directed_edges"]}
    metrics = get("http://127.0.0.1:9090/api/v1/query", query='count(count by(service_name) (traces_span_metrics_calls_total{span_kind="SPAN_KIND_SERVER"}))')
    assert float(metrics["data"]["result"][0]["value"][1]) == 10
    result["checks"]["prometheus_server_services"] = 10
    dashboards = get("http://127.0.0.1:3000/api/search", type="dash-db")
    expected = {"service-overview", "distributed-overview", "mutation-experiments"}
    assert expected <= {d["uid"] for d in dashboards}
    result["checks"]["grafana_dashboards"] = sorted(expected)
    queries = 0
    for uid in expected:
        dashboard = get(f"http://127.0.0.1:3000/api/dashboards/uid/{uid}")["dashboard"]
        for panel in dashboard["panels"]:
            for target in panel.get("targets", []):
                query = get("http://127.0.0.1:9090/api/v1/query", query=target["expr"])
                assert query["status"] == "success"
                queries += 1
    result["checks"]["valid_panel_queries"] = queries
    Path("data/validation").mkdir(parents=True, exist_ok=True)
    Path("data/validation/live-smoke.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
