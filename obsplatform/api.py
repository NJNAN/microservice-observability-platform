import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response

from . import mutations
from .experiments import latest_summary
from .storage import experiments
from .telemetry import metrics

app = FastAPI(title="Microservice Observability Platform", version="1.0.0")


@app.get("/health")
def health():
    return {"status": "ok", "mutation_execution": os.getenv("MOP_ALLOW_MUTATIONS") == "1"}


@app.get("/api/services")
def services():
    return {"services": latest_summary()["observed_services"], "source": "last collected trace window"}


@app.get("/api/topology")
def topology():
    s = latest_summary()
    return {k: s.get(k, []) for k in ("nodes", "edges", "rpc_calls")}


@app.get("/api/traces/summary")
def summary():
    return latest_summary()


@app.get("/api/mutations")
def mutation_list():
    return mutations.catalog()


def check_mutation(case_id):
    if mutations.case_by_id(case_id) is None:
        raise HTTPException(404, "Unknown mutation")
    if os.getenv("MOP_ALLOW_MUTATIONS") != "1":
        raise HTTPException(403, "Set MOP_ALLOW_MUTATIONS=1 in an isolated local lab")


@app.post("/api/mutations/{case_id}/run")
def mutation_run(case_id: str):
    check_mutation(case_id)
    try:
        result = mutations.run(case_id)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc
    if result["status"] != "complete":
        raise HTTPException(500, result)
    return result


@app.post("/api/mutations/{case_id}/restore")
def mutation_restore(case_id: str):
    check_mutation(case_id)
    try:
        return mutations.restore(case_id)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc


@app.get("/api/experiments")
def experiment_list():
    return experiments()


@app.get("/api/experiments/{experiment_id}")
def experiment_detail(experiment_id: str):
    result = next((r for r in experiments() if r["id"] == experiment_id), None)
    if result is None:
        raise HTTPException(404, "Unknown experiment")
    return result


@app.get("/metrics")
def prometheus_metrics():
    return Response(metrics(), media_type="text/plain; version=0.0.4")
