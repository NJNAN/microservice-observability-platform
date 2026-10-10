import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from obsplatform import mutations, settings, storage
from obsplatform.api import app
from obsplatform.topology import passes, reconstruct

ROOT = Path(__file__).resolve().parents[1]


def fixture_trace():
    return json.loads((ROOT / "cia_preexperiment_v2/results/raw/online_boutique_trace_gate/run_01.traces.json").read_text())["data"]


def test_historical_trace_reconstruction():
    s = reconstruct(fixture_trace())
    assert len(s["nodes"]) == 10
    assert len(s["edges"]) == 14
    assert s["matched_client_server_span_count"] == 71
    assert sum(r["calls"] for r in s["rpc_calls"]) == 71
    assert passes(s, {"rows": [{"status": 200, "error": None}]})
    assert not passes(s, {"rows": []})
    assert not passes(s, {"rows": [{"status": 500, "error": None}]})


def test_broken_pair_rejected():
    traces = fixture_trace()
    for trace in traces:
        for span in trace["spans"]:
            if any(t["key"] == "span.kind" and t["value"] == "server" for t in span.get("tags", [])):
                span["references"] = []
    assert not passes(reconstruct(traces), {"rows": [{"status": 200, "error": None}]})


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "DATA", tmp_path)
    monkeypatch.setattr(storage, "DATA", tmp_path)
    return tmp_path


def test_api_empty_and_not_found(isolated):
    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert client.get("/api/topology").json()["edges"] == []
    assert len(client.get("/api/mutations").json()) == 23
    assert client.get("/api/experiments/unknown").status_code == 404
    assert client.post("/api/mutations/unknown/run").status_code == 404
    assert client.post("/api/mutations/C01_catalog_price/run").status_code == 403
    assert client.get("/metrics").status_code == 200


def test_exclusive_lock_and_recovery(isolated):
    with mutations.exclusive():
        with pytest.raises(RuntimeError):
            with mutations.exclusive():
                pass
    assert not (isolated / "operation.lock").exists()


def test_restore_replaces_entire_template(monkeypatch, isolated):
    baseline = {"metadata": {"labels": {"app": "frontend"}}, "spec": {"containers": [{"name": "server", "image": "baseline"}]}}
    storage.save(isolated / "active.json", {"state": "active", "case_id": "C", "service": "frontend", "template": baseline})
    calls = []

    def fake(*args, **kwargs):
        calls.append(args)
        if args[0] == "get":
            return json.dumps({"spec": {"template": baseline}})
        return ""

    monkeypatch.setattr(mutations, "kubectl", fake)
    assert mutations.restore("C")["state"] == "baseline"
    assert "--type=json" in calls[0]
    patch = json.loads(calls[0][-1])
    assert patch[0]["path"] == "/spec/template" and patch[0]["op"] == "replace"


def test_run_restores_on_collection_error(monkeypatch, isolated):
    baseline = {"spec": {"containers": [{"name": "server"}]}}
    monkeypatch.setattr(mutations, "kubectl", lambda *a, **k: json.dumps({"spec": {"template": copy.deepcopy(baseline)}}))
    monkeypatch.setattr(mutations, "apply_override", lambda *a: None)
    restored = []
    monkeypatch.setattr(mutations, "patch_template", lambda *a: restored.append(a))

    def fail(*args):
        raise RuntimeError("Jaeger unavailable")

    monkeypatch.setattr(mutations, "collect", fail)
    result = mutations.run("C01_catalog_price")
    assert restored and result["restored"]
    assert result["status"] == "restore_failed"
    assert "Jaeger unavailable" in result["error"]
    assert (isolated / result["id"] / "result.json").exists()


def test_restore_failure_keeps_journal(monkeypatch, isolated):
    storage.save(isolated / "active.json", {"state": "active", "case_id": "C", "service": "frontend", "template": {}})

    def fail(*args):
        raise RuntimeError("Kubernetes unavailable")

    monkeypatch.setattr(mutations, "patch_template", fail)
    with pytest.raises(RuntimeError):
        mutations.restore("C")
    assert (isolated / "active.json").exists()
