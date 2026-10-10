import json
import time

from . import settings
from .storage import save
from .topology import execute, fetch_traces, passes, reconstruct


def collect(out):
    start = int(time.time() * 1e6)
    workload = execute(settings.FRONTEND, 1, 0.2)
    end = int(time.time() * 1e6) + 1000000
    time.sleep(8)
    traces = fetch_traces(settings.JAEGER, start, end)
    summary = reconstruct(traces)
    summary.update(collected_at=time.time(), query_start_us=start, query_end_us=end)
    result = {"collected_at": time.time(), "query_start_us": start, "query_end_us": end,
              "workload": workload, "summary": summary, "gate_pass": passes(summary, workload)}
    save(out / "traces.json", {"data": traces})
    save(out / "collection.json", result)
    return result


def latest_summary():
    path = settings.DATA / "latest.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {
        "observed_services": [], "nodes": [], "edges": [], "trace_count": 0,
        "note": "No V1 collection yet. Run the demo or a mutation; historical data is not served as live data."}
