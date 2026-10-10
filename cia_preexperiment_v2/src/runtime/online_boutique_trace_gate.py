"""Run the fixed Online Boutique journey and audit complete Jaeger service chains."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import requests

from gate_workload import execute

SERVICES = (
    "adservice", "cartservice", "shippingservice", "emailservice",
    "checkoutservice", "productcatalogservice", "currencyservice",
    "paymentservice", "recommendationservice", "frontend",
)


def span_kind(span: dict) -> str | None:
    return next((tag["value"] for tag in span.get("tags", []) if tag["key"] == "span.kind"), None)


def audit(traces: list[dict]) -> dict:
    export_operation = "opentelemetry.proto.collector.trace.v1.TraceService/Export"
    internal_traces = [trace for trace in traces if trace.get("spans") and all(
        span["operationName"] == export_operation for span in trace["spans"])]
    business_traces = [trace for trace in traces if trace not in internal_traces]
    all_services: set[str] = set()
    server_edges: Counter[tuple[str, str]] = Counter()
    edge_trace_ids: dict[tuple[str, str], set[str]] = {}
    broken_references = []
    roots_by_service: Counter[str] = Counter()
    client_parent_edges = 0
    business_client_spans = 0
    matched_client_server_spans = 0
    unmatched_client_spans = []
    triple_chains = []
    ancestral_paths = []
    span_count = 0

    for trace in business_traces:
        trace_id = trace["traceID"]
        processes = {key: value["serviceName"] for key, value in trace.get("processes", {}).items()}
        spans = {span["spanID"]: span for span in trace.get("spans", [])}
        children_by_parent: dict[str, list[dict]] = {}
        for span in spans.values():
            for ref in span.get("references", []):
                if ref.get("refType") == "CHILD_OF":
                    children_by_parent.setdefault(ref["spanID"], []).append(span)
        span_count += len(spans)
        all_services.update(processes.values())
        trace_edges: set[tuple[str, str]] = set()
        for span in spans.values():
            service = processes[span["processID"]]
            if span_kind(span) == "client" and "hipstershop." in span["operationName"]:
                business_client_spans += 1
                matched = any(
                    span_kind(child) == "server"
                    and processes[child["processID"]] != service
                    for child in children_by_parent.get(span["spanID"], [])
                )
                if matched:
                    matched_client_server_spans += 1
                else:
                    unmatched_client_spans.append({"trace_id": trace_id, "service": service,
                                                   "operation": span["operationName"], "span_id": span["spanID"]})
            refs = [ref for ref in span.get("references", []) if ref.get("refType") == "CHILD_OF"]
            if not refs and service in SERVICES:
                roots_by_service[service] += 1
            for ref in refs:
                parent = spans.get(ref["spanID"])
                if parent is None:
                    broken_references.append({"trace_id": trace_id, "span_id": span["spanID"],
                                              "service": service, "missing_parent_id": ref["spanID"]})
                    continue
                source = processes[parent["processID"]]
                target = service
                if source == target or source not in SERVICES or target not in SERVICES:
                    continue
                if span_kind(span) != "server":
                    continue
                server_edges[(source, target)] += 1
                edge_trace_ids.setdefault((source, target), set()).add(trace_id)
                trace_edges.add((source, target))
                if span_kind(parent) == "client":
                    client_parent_edges += 1
        for left, middle in sorted(trace_edges):
            for middle2, right in sorted(trace_edges):
                if middle == middle2 and len({left, middle, right}) == 3:
                    triple_chains.append({"trace_id": trace_id, "services": [left, middle, right]})
        for span in spans.values():
            if span_kind(span) != "server":
                continue
            chain = []
            seen = set()
            current = span
            while current and current["spanID"] not in seen:
                seen.add(current["spanID"])
                service = processes[current["processID"]]
                if not chain or chain[-1] != service:
                    chain.append(service)
                refs = [ref for ref in current.get("references", []) if ref.get("refType") == "CHILD_OF"]
                current = spans.get(refs[0]["spanID"]) if refs else None
            path = list(reversed(chain))
            if len(path) >= 3 and path[0] == "frontend" and len(set(path)) >= 3:
                ancestral_paths.append({"trace_id": trace_id, "leaf_span_id": span["spanID"],
                                        "services": path})

    return {
        "raw_trace_count": len(traces),
        "raw_span_count": sum(len(trace.get("spans", [])) for trace in traces),
        "excluded_telemetry_export_traces": len(internal_traces),
        "trace_count": len(business_traces),
        "span_count": span_count,
        "observed_services": sorted(set(SERVICES) & all_services),
        "missing_services": sorted(set(SERVICES) - all_services),
        "other_process_services": sorted(all_services - set(SERVICES)),
        "unique_cross_service_directed_edges": len(server_edges),
        "edges": [{"source": source, "target": target, "call_count": count,
                   "trace_count": len(edge_trace_ids[(source, target)])}
                  for (source, target), count in sorted(server_edges.items())],
        "server_edges_with_client_parent": client_parent_edges,
        "business_grpc_client_span_count": business_client_spans,
        "matched_client_server_span_count": matched_client_server_spans,
        "unmatched_client_span_count": len(unmatched_client_spans),
        "unmatched_client_spans": unmatched_client_spans,
        "broken_parent_reference_count": len(broken_references),
        "broken_parent_references": broken_references,
        "root_spans_by_service": dict(sorted(roots_by_service.items())),
        "frontend_to_second_downstream_chains": triple_chains,
        "verified_ancestral_service_paths": ancestral_paths,
    }


def fetch_traces(jaeger: str, start_us: int, end_us: int) -> list[dict]:
    traces: dict[str, dict] = {}
    for service in SERVICES:
        response = requests.get(jaeger + "/api/traces", params={
            "service": service, "start": start_us, "end": end_us, "limit": 1000,
        }, timeout=30)
        response.raise_for_status()
        for trace in response.json().get("data", []):
            traces[trace["traceID"]] = trace
    return sorted(traces.values(), key=lambda trace: trace["traceID"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18080")
    parser.add_argument("--jaeger", default="http://127.0.0.1:16686")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--settle-seconds", type=float, default=8)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    summaries = []
    for run_id in range(1, args.runs + 1):
        start_us = int(time.time() * 1_000_000) - 1_000_000
        workload = execute(args.base_url, repeats=1, interval_s=0.2)
        end_us = int(time.time() * 1_000_000) + 2_000_000
        time.sleep(args.settle_seconds)
        traces = fetch_traces(args.jaeger, start_us, end_us)
        summary = audit(traces)
        summary.update({
            "run_id": run_id,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "workload_success_count": sum(row["status"] == 200 for row in workload["rows"]),
            "workload_request_count": len(workload["rows"]),
            "workload_transport_errors": sum(row["error"] is not None for row in workload["rows"]),
            "query_start_us": start_us,
            "query_end_us": end_us,
        })
        prefix = args.out_dir / f"run_{run_id:02d}"
        (prefix.with_suffix(".workload.json")).write_text(json.dumps(workload, indent=2), encoding="utf-8")
        (prefix.with_suffix(".traces.json")).write_text(json.dumps({"data": traces}, indent=2), encoding="utf-8")
        (prefix.with_suffix(".summary.json")).write_text(json.dumps(summary, indent=2), encoding="utf-8")
        summaries.append(summary)
        print(json.dumps({key: summary[key] for key in (
            "run_id", "trace_count", "span_count", "observed_services",
            "unique_cross_service_directed_edges", "broken_parent_reference_count",
            "unmatched_client_span_count", "root_spans_by_service",
            "workload_success_count")}, ensure_ascii=False), flush=True)
    passed = all(
        summary["workload_success_count"] == 5
        and summary["workload_transport_errors"] == 0
        and len(summary["observed_services"]) == len(SERVICES)
        and summary["unique_cross_service_directed_edges"] >= 10
        and summary["broken_parent_reference_count"] == 0
        and summary["unmatched_client_span_count"] == 0
        and set(summary["root_spans_by_service"]) <= {"frontend"}
        and summary["verified_ancestral_service_paths"]
        for summary in summaries
    )
    result = {"decision": "TRACE GATE PASS" if passed else "TRACE GATE FAIL", "runs": summaries}
    (args.out_dir / "gate_summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(result["decision"])
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
