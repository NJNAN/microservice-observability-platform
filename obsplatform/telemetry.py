"""Durable experiment metrics, derived from persisted evidence on every scrape."""
import json
import os

from prometheus_client import CollectorRegistry, Gauge, generate_latest

from .storage import experiments


def metrics():
    registry = CollectorRegistry()
    if os.getenv("KUBERNETES_SERVICE_HOST"):
        from .mutations import kubectl
        from .topology import SERVICES
        ready = Gauge("mop_service_ready", "Kubernetes deployment has an available replica", ["service"], registry=registry)
        try:
            deployments = json.loads(kubectl("get", "deployments", "-o", "json"))["items"]
            for d in deployments:
                if d["metadata"]["name"] in SERVICES:
                    ready.labels(d["metadata"]["name"]).set(int(d.get("status", {}).get("availableReplicas", 0) > 0))
        except (RuntimeError, OSError):
            pass  # Missing telemetry is preferable to fabricated health.
    runs = Gauge("mop_mutation_runs", "Persisted runs by final orchestration outcome", ["outcome"], registry=registry)
    workload = Gauge("mop_workload_success_ratio", "Latest experiment HTTP success fraction", ["phase"], registry=registry)
    traces = Gauge("mop_trace_collection_count", "Persisted traces across experiment phases", registry=registry)
    info = Gauge("mop_experiment_info", "Latest experiment metadata", ["case_id", "change_type", "service", "status"], registry=registry)
    errors = Gauge("mop_detected_errors", "Latest workload failures", ["phase"], registry=registry)
    duration = Gauge("mop_workload_duration_ms", "Mean workload request duration", ["phase"], registry=registry)
    timestamp = Gauge("mop_experiment_timestamp_seconds", "Latest experiment start time", registry=registry)
    records = experiments()
    for outcome in ("complete", "error", "restore_failed", "running"):
        runs.labels(outcome).set(sum(r["status"] == outcome for r in records))
    traces.set(sum(p.get("summary", {}).get("trace_count", 0) for r in records for p in r.get("phases", {}).values()))
    if records:
        r = records[0]
        info.labels(r["case_id"], r["change_type"], r["service"], r["status"]).set(1)
        timestamp.set(r["started"])
        for phase, p in r.get("phases", {}).items():
            rows = p["workload"]["rows"]
            ok = sum(x["status"] == 200 for x in rows)
            workload.labels(phase).set(ok / len(rows) if rows else 0)
            errors.labels(phase).set(len(rows) - ok)
            duration.labels(phase).set(sum(x["latency_ms"] for x in rows) / len(rows) if rows else 0)
    return generate_latest(registry)
