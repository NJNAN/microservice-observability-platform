"""Export and audit measured Jaeger traces for the execution gate."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import requests


def summarize(payload: dict) -> dict:
    traces = payload.get("data", [])
    observed_services: set[str] = set()
    edge_calls: Counter[tuple[str, str]] = Counter()
    methods: Counter[str] = Counter()
    incomplete_parent_refs = 0
    for trace in traces:
        processes = {pid: p["serviceName"] for pid, p in trace.get("processes", {}).items()}
        spans = {span["spanID"]: span for span in trace.get("spans", [])}
        observed_services.update(processes.values())
        for span in spans.values():
            methods[span["operationName"]] += 1
            for ref in span.get("references", []):
                if ref.get("refType") != "CHILD_OF":
                    continue
                parent = spans.get(ref["spanID"])
                if parent is None:
                    incomplete_parent_refs += 1
                    continue
                source = processes[parent["processID"]]
                target = processes[span["processID"]]
                if source != target:
                    edge_calls[(source, target)] += 1
    return {
        "trace_count": len(traces),
        "span_count": sum(len(t.get("spans", [])) for t in traces),
        "observed_process_services": sorted(observed_services),
        "distinct_cross_service_parent_child_edges": len(edge_calls),
        "cross_service_parent_child_calls": [
            {"source": source, "target": target, "count": count}
            for (source, target), count in sorted(edge_calls.items())
        ],
        "incomplete_parent_refs": incomplete_parent_refs,
        "top_operations": methods.most_common(30),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--jaeger", default="http://127.0.0.1:16686")
    parser.add_argument("--service", default="frontend")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--summary-out", type=Path, required=True)
    args = parser.parse_args()
    response = requests.get(args.jaeger + "/api/traces", params={"service": args.service, "limit": 500}, timeout=30)
    response.raise_for_status()
    payload = response.json()
    summary = summarize(payload)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    args.summary_out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("trace_count", "span_count", "observed_process_services", "distinct_cross_service_parent_child_edges", "incomplete_parent_refs")}, ensure_ascii=False))
