"""Reuse the validated multilingual parent/child audit, without research scoring."""
import sys
from collections import Counter

from .settings import LEGACY

sys.path.insert(0, str(LEGACY / "src/runtime"))
from online_boutique_trace_gate import SERVICES, audit, fetch_traces  # noqa: E402,F401
from gate_workload import execute  # noqa: E402,F401


def reconstruct(traces):
    result = audit(traces)
    operations = Counter()
    for trace in traces:
        spans = {s["spanID"]: s for s in trace.get("spans", [])}
        processes = trace.get("processes", {})
        for span in spans.values():
            tags = {t["key"]: t["value"] for t in span.get("tags", [])}
            if tags.get("span.kind") != "server":
                continue
            for ref in span.get("references", []):
                parent = spans.get(ref["spanID"])
                if ref.get("refType") != "CHILD_OF" or parent is None:
                    continue
                source = processes[parent["processID"]]["serviceName"]
                target = processes[span["processID"]]["serviceName"]
                if source != target and source in SERVICES and target in SERVICES:
                    operations[source, target, span["operationName"]] += 1
    result["nodes"] = [{"id": s} for s in result["observed_services"]]
    result["rpc_calls"] = [dict(source=s, target=t, operation=o, calls=n)
                           for (s, t, o), n in sorted(operations.items())]
    for edge in result["edges"]:
        edge["calls"] = edge["call_count"]
    return result


def passes(summary, workload):
    rows = workload.get("rows", [])
    return bool(rows) and all(r["status"] == 200 and not r["error"] for r in rows) and (
        set(summary["observed_services"]) == set(SERVICES)
        and summary["unique_cross_service_directed_edges"] >= 14
        and summary["business_grpc_client_span_count"] > 0
        and summary["matched_client_server_span_count"] == summary["business_grpc_client_span_count"]
        and summary["broken_parent_reference_count"] == 0
        and summary["unmatched_client_span_count"] == 0
    )
