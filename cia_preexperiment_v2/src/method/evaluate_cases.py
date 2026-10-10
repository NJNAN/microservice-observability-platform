"""Frozen-rule service/API CIA evaluation from independent behavior oracles."""

import csv
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from protocol import (
    API_OWNERS, API_UNIVERSE, SERVICE_UNIVERSE, STATIC_CALLS,
    IGNORED_RESPONSE_EDGES, PRICE_FIELD_UNUSED_EDGES,
    MAX_STATIC_API_DISTANCE, FREQUENT_EDGE_MIN_CALLS,
    HYBRID_STATIC_ONLY_LOW_COVERAGE_SCORE, HYBRID_STATIC_ONLY_MID_COVERAGE_SCORE,
    HYBRID_STATIC_ONLY_HIGH_COVERAGE_SCORE, HYBRID_RUNTIME_ONLY_SCORE,
    HYBRID_BOTH_SCORE, HYBRID_THRESHOLD, LOW_COVERAGE_CUTOFF,
    HIGH_COVERAGE_CUTOFF, source_seeds,
)

ROOT = Path(__file__).resolve().parents[2]
CASES = json.loads((ROOT / "data/mutations/method_controlled/cases.json").read_text(encoding="utf-8"))
REAL_MANIFEST = ROOT / "data/commits/method_replays/cases.json"
if REAL_MANIFEST.exists():
    CASES += json.loads(REAL_MANIFEST.read_text(encoding="utf-8"))
RAW = ROOT / "results/raw"
TABLES = ROOT / "results/tables/method_experiment"
TABLES.mkdir(parents=True, exist_ok=True)
METHODS = ("B0", "B1", "B2", "B3", "B4", "B5")
COVERAGE_LEVELS = ("low", "medium", "high")


def case_path(case):
    cohort_dir = "method_controlled" if case["cohort"] == "controlled" else "method_real_replays"
    return RAW / cohort_dir / case["case_id"]


def tag(span, key):
    for item in span.get("tags", []):
        if item["key"] == key:
            return item["value"]
    return None


def canonical_api(service, span):
    if tag(span, "span.kind") != "server":
        return None
    if service == "frontend":
        method, path = tag(span, "http.method"), tag(span, "http.target")
        if method == "GET" and path == "/": return "frontend.GET_home"
        if method == "GET" and path and path.startswith("/product/"): return "frontend.GET_product"
        if method == "POST" and path == "/cart": return "frontend.POST_cart"
        if method == "GET" and path == "/cart": return "frontend.GET_cart"
        if method == "POST" and path == "/cart/empty": return "frontend.POST_cart_empty"
        if method == "POST" and path == "/setCurrency": return "frontend.POST_set_currency"
        if method == "GET" and path == "/logout": return "frontend.GET_logout"
        if method == "POST" and path == "/cart/checkout": return "frontend.POST_checkout"
        if method == "GET" and path and path.startswith("/product-meta/"): return "frontend.GET_product_meta"
        if method == "GET" and path == "/assistant": return "frontend.GET_assistant"
        if method == "POST" and path == "/bot": return "frontend.POST_bot"
        return None
    name = span.get("operationName", "")
    if "hipstershop." not in name:
        return None
    name = name.split("hipstershop.", 1)[1].replace("/", ".", 1)
    return name if name in API_OWNERS else None


def trace_route(trace):
    processes = {key: p["serviceName"] for key, p in trace.get("processes", {}).items()}
    for span in trace.get("spans", []):
        if processes[span["processID"]] == "frontend" and tag(span, "span.kind") == "server":
            return canonical_api("frontend", span)
    return None


def select_traces(all_traces, level):
    business = [trace for trace in all_traces if trace_route(trace)]
    if level == "high": return business
    wanted = {"frontend.POST_cart"}
    if level == "medium":
        wanted |= {"frontend.GET_home", "frontend.GET_product"}
    return [trace for trace in business if trace_route(trace) in wanted]


def trace_graph(traces):
    api_edges = Counter()
    service_edges = Counter()
    observed_apis = set()
    observed_services = set()
    for trace in traces:
        processes = {key: p["serviceName"] for key, p in trace.get("processes", {}).items()}
        spans = {s["spanID"]: s for s in trace.get("spans", [])}
        for span in spans.values():
            target_service = processes[span["processID"]]
            target_api = canonical_api(target_service, span)
            if target_api is None:
                continue
            observed_apis.add(target_api)
            observed_services.add(target_service)
            refs = [r for r in span.get("references", []) if r.get("refType") == "CHILD_OF"]
            current = spans.get(refs[0]["spanID"]) if refs else None
            while current is not None:
                if tag(current, "span.kind") == "server":
                    source_service = processes[current["processID"]]
                    source_api = canonical_api(source_service, current)
                    if source_api and source_service != target_service:
                        api_edges[(source_api, target_api)] += 1
                        service_edges[(source_service, target_service)] += 1
                    break
                refs = [r for r in current.get("references", []) if r.get("refType") == "CHILD_OF"]
                current = spans.get(refs[0]["spanID"]) if refs else None
    return api_edges, service_edges, observed_apis, observed_services


def reverse_reachable(seeds, edges, max_distance=None):
    answer = set(seeds)
    frontier = set(seeds)
    distance = 0
    while frontier and (max_distance is None or distance < max_distance):
        next_frontier = {caller for caller, callee in edges if callee in frontier and caller not in answer}
        answer |= next_frontier
        frontier = next_frontier
        distance += 1
    return answer


def static_predictions(case):
    seeds = source_seeds(case)
    service_edges = {(API_OWNERS[caller], API_OWNERS[callee])
                     for caller, callees in STATIC_CALLS.items() for callee in callees
                     if API_OWNERS[caller] != API_OWNERS[callee]}
    s1_services = reverse_reachable({case["changed_service"]}, service_edges)
    s1_apis = {api for api, owner in API_OWNERS.items() if owner in s1_services}
    typed_edges = set()
    for caller, callees in STATIC_CALLS.items():
        for callee in callees:
            edge = (caller, callee)
            if edge in IGNORED_RESPONSE_EDGES:
                continue
            if (case["case_id"] == "C01_catalog_price" or case["case_id"].startswith(("R01", "R02"))) and edge in PRICE_FIELD_UNUSED_EDGES:
                continue
            typed_edges.add(edge)
    s2_apis = reverse_reachable(seeds, typed_edges, MAX_STATIC_API_DISTANCE)
    return s1_apis, s2_apis


def predictions(case, graph, api_coverage):
    api_edges, service_edges, observed_apis, observed_services = graph
    seeds = source_seeds(case)
    s1, s2 = static_predictions(case)
    r1 = reverse_reachable(seeds, set(api_edges))
    r2 = reverse_reachable(seeds, {edge for edge, count in api_edges.items() if count >= FREQUENT_EDGE_MIN_CALLS})
    b0 = {api for api, owner in API_OWNERS.items() if owner == case["changed_service"]}
    if api_coverage < LOW_COVERAGE_CUTOFF:
        static_only_score = HYBRID_STATIC_ONLY_LOW_COVERAGE_SCORE
    elif api_coverage < HIGH_COVERAGE_CUTOFF:
        static_only_score = HYBRID_STATIC_ONLY_MID_COVERAGE_SCORE
    else:
        static_only_score = HYBRID_STATIC_ONLY_HIGH_COVERAGE_SCORE
    hybrid = set()
    for api in API_UNIVERSE:
        if api in s2 and api in r1: score = HYBRID_BOTH_SCORE
        elif api in r1: score = HYBRID_RUNTIME_ONLY_SCORE
        elif api in s2: score = static_only_score
        else: score = 0
        if score >= HYBRID_THRESHOLD:
            hybrid.add(api)
    return {"B0": b0, "B1": s1, "B2": s2, "B3": r1, "B4": r2, "B5": hybrid}


def stable_value(path, phase, key, source):
    values = []
    for repeat in range(1, 4):
        p = path / f"{phase}_{repeat:02d}.oracle.json"
        oracle = json.loads(p.read_text(encoding="utf-8"))
        if key in oracle[source]:
            value = oracle[source][key]
            if key == "RecommendationService.ListRecommendations" and value.get("status") == "OK":
                ids = value.get("result", {}).get("product_ids", [])
                excluded = {"66VCHSJNUP", "1YMWWN1N4O", "L9ECAV7KIM", "2ZYFJ3GM2N", "0PUK6V6EV0", "LS4PSXUNUM", "9SIQT8TOJO", "6E92ZMYYFZ"}
                # The service intentionally samples products. The fixed oracle
                # concerns list size and whether excluded IDs leak through.
                value = {"status": "OK", "count": len(ids), "contains_excluded": bool(set(ids) & excluded)}
            values.append(value)
    if len(values) != 3 or any(value != values[0] for value in values):
        return None
    return values[0]


def ground_truth(case):
    path = case_path(case)
    labels = {api: "Unknown" for api in API_UNIVERSE}
    evidence = {}
    for api in API_UNIVERSE:
        source = "http" if api.startswith("frontend.") else "grpc"
        first = json.loads((path / "original_01.oracle.json").read_text(encoding="utf-8"))[source]
        probe_keys = sorted(key for key in first if key == api or key.startswith(api + "."))
        if not probe_keys:
            continue
        old, new = [], []
        for key in probe_keys:
            before = stable_value(path, "original", key, source)
            after = stable_value(path, "changed", key, source)
            if before is None or after is None:
                break
            old.append(before)
            new.append(after)
        else:
            labels[api] = "Impacted" if old != new else "Not Impacted"
            evidence[api] = {"probes": probe_keys, "original": old, "changed": new}
    # The fixed workflow explicitly probes POST /cart status, independent of
    # HTML hash and the subsequent redirected GET /cart response.
    before_statuses = [next(row["status"] for row in json.loads((path / f"original_{i:02d}.workload.json").read_text(encoding="utf-8"))["rows"] if row["step"] == "add_cart") for i in range(1, 4)]
    after_statuses = [next(row["status"] for row in json.loads((path / f"changed_{i:02d}.workload.json").read_text(encoding="utf-8"))["rows"] if row["step"] == "add_cart") for i in range(1, 4)]
    if len(set(before_statuses)) == len(set(after_statuses)) == 1:
        labels["frontend.POST_cart"] = "Impacted" if before_statuses[0] != after_statuses[0] else "Not Impacted"
        evidence["frontend.POST_cart"] = {"probes": ["workload.add_cart.status"], "original": before_statuses, "changed": after_statuses}
    services = {}
    for service in SERVICE_UNIVERSE:
        owned = [labels[api] for api, owner in API_OWNERS.items() if owner == service]
        if "Impacted" in owned:
            services[service] = "Impacted"
        elif "Unknown" in owned:
            services[service] = "Unknown"
        else:
            services[service] = "Not Impacted"
    return labels, services, evidence


def confusion(predicted, labels):
    known = {obj for obj, label in labels.items() if label != "Unknown"}
    positives = {obj for obj in known if labels[obj] == "Impacted"}
    p = predicted & known
    tp = len(p & positives)
    fp = len(p - positives)
    fn = len(positives - p)
    tn = len(known - (p | positives))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": precision, "recall": recall, "f1": f1, "known": len(known), "positive": len(positives)}


def write_csv(path, rows):
    if not rows: return
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def evaluate_case(case):
    api_labels, service_labels, evidence = ground_truth(case)
    case_dir = case_path(case)
    (case_dir / "ground_truth.json").write_text(json.dumps({"api_labels": api_labels, "service_labels": service_labels, "evidence": evidence}, indent=2), encoding="utf-8")
    rows, errors = [], []
    for repeat in range(1, 4):
        traces = json.loads((case_dir / f"original_{repeat:02d}.traces.json").read_text(encoding="utf-8"))["data"]
        for level in COVERAGE_LEVELS:
            chosen = select_traces(traces, level)
            graph = trace_graph(chosen)
            api_edges, service_edges, observed_apis, observed_services = graph
            api_coverage = len(observed_apis) / len(API_UNIVERSE)
            service_coverage = len(observed_services) / len(SERVICE_UNIVERSE)
            static_service_edges = {(API_OWNERS[caller], API_OWNERS[callee])
                                    for caller, callees in STATIC_CALLS.items() for callee in callees
                                    if API_OWNERS[caller] != API_OWNERS[callee]}
            edge_coverage = len(set(service_edges) & static_service_edges) / len(static_service_edges)
            methods = predictions(case, graph, api_coverage)
            for method, predicted_apis in methods.items():
                predicted_services = {API_OWNERS[api] for api in predicted_apis}
                for granularity, predicted, labels in (
                    ("api", predicted_apis, api_labels),
                    ("service", predicted_services, service_labels),
                ):
                    metrics = confusion(predicted, labels)
                    rows.append({
                        "case_id": case["case_id"], "cohort": case["cohort"], "change_type": case["change_type"],
                        "changed_service": case["changed_service"], "repeat": repeat,
                        "coverage_level": level, "service_coverage": service_coverage,
                        "api_coverage": api_coverage, "static_edge_coverage": edge_coverage,
                        "granularity": granularity, "method": method, **metrics,
                    })
            for granularity, labels in (("api", api_labels), ("service", service_labels)):
                known = {obj for obj, label in labels.items() if label != "Unknown"}
                positives = {obj for obj in known if labels[obj] == "Impacted"}
                s = methods["B2"] & known if granularity == "api" else {API_OWNERS[a] for a in methods["B2"]} & known
                r = methods["B3"] & known if granularity == "api" else {API_OWNERS[a] for a in methods["B3"]} & known
                r4 = methods["B4"] & known if granularity == "api" else {API_OWNERS[a] for a in methods["B4"]} & known
                h = methods["B5"] & known if granularity == "api" else {API_OWNERS[a] for a in methods["B5"]} & known
                errors.append({
                    "case_id": case["case_id"], "cohort": case["cohort"], "change_type": case["change_type"],
                    "repeat": repeat, "coverage_level": level, "granularity": granularity,
                    "static_fp": len(s - positives), "static_fn": len(positives - s),
                    "runtime_fp": len(r - positives), "runtime_fn": len(positives - r),
                    "static_fp_corrected": len((s - positives) - h),
                    "runtime_fn_recovered": len((positives - r) & h),
                    "hybrid_induced_fp": len((h - positives) - (s - positives | r - positives)),
                    "hybrid_induced_fn": len((positives - h) - ((positives - s) | (positives - r))),
                    "hybrid_added_fp_vs_B2": len((h - positives) - (s - positives)),
                    "hybrid_added_fn_vs_B2": len((positives - h) - (positives - s)),
                    "hybrid_added_fp_vs_B4": len((h - positives) - (r4 - positives)),
                    "hybrid_added_fn_vs_B4": len((positives - h) - (positives - r4)),
                    "hybrid_fp": len(h - positives), "hybrid_fn": len(positives - h),
                    "static_runtime_error_overlap": len(((s - positives) | (positives - s)) & ((r - positives) | (positives - r))),
                })
    return rows, errors


def main():
    all_rows, all_errors, failed, excluded = [], [], [], []
    for case in CASES:
        path = case_path(case) / "progress.json"
        if not path.exists() or json.loads(path.read_text(encoding="utf-8"))["status"] != "complete":
            failed.append(case["case_id"])
            continue
        try:
            api_labels, _, _ = ground_truth(case)
            if "Impacted" not in api_labels.values():
                excluded.append(case["case_id"])
                continue
            rows, errors = evaluate_case(case)
            all_rows.extend(rows)
            all_errors.extend(errors)
        except Exception as exc:
            failed.append(f"{case['case_id']}: {exc}")
    write_csv(TABLES / "scores.csv", all_rows)
    write_csv(TABLES / "errors.csv", all_errors)
    status = {"evaluated_cases": len(set(row["case_id"] for row in all_rows)), "excluded_no_observable_change": excluded, "failed_or_incomplete": failed, "score_rows": len(all_rows)}
    (TABLES / "evaluation_status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    print(json.dumps(status, indent=2))


if __name__ == "__main__":
    main()
