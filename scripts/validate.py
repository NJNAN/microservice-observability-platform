"""Offline consistency checks, supplemented by kubectl dry-run in CI."""
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def main():
    docs = list(yaml.safe_load_all((ROOT / "k8s/application/application.yaml").read_text()))
    deployments = [d for d in docs if d["kind"] == "Deployment"]
    assert len(deployments) == 11, "Ten application services plus Redis required"
    for deployment in deployments:
        name = deployment["metadata"]["name"]
        env = {e["name"]: e.get("value") for e in deployment["spec"]["template"]["spec"]["containers"][0].get("env", [])}
        if name != "redis-cart":
            assert "otel-collector:" in env["COLLECTOR_SERVICE_ADDR"]
    cases = json.loads((ROOT / "configs/mutations.json").read_text())
    assert len(cases) == 23 and len({c["case_id"] for c in cases}) == 23
    for c in cases:
        for key in ("original", "changed"):
            if c[key]:
                assert (ROOT / c[key]).is_file(), c[key]
    dashboards = list((ROOT / "dashboards").glob("*.json"))
    assert len(dashboards) == 3
    for path in dashboards:
        doc = json.loads(path.read_text())
        assert doc["panels"] and doc["uid"]
    for path in (ROOT / "k8s").rglob("*.yaml"):
        list(yaml.safe_load_all(path.read_text()))
    print("Configuration validation passed: 10 apps, 23 cases, 3 dashboards")


if __name__ == "__main__":
    main()
