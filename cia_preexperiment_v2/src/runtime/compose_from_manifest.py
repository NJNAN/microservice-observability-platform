"""Translate the pinned official Online Boutique release manifest to a local gate Compose file.

This is deployment translation, not a change to application source. Images and
application environment are copied from the official release manifest; tracing
and host-facing ports are the only local additions.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml


def generate(manifest: Path) -> dict:
    documents = list(yaml.safe_load_all(manifest.read_text(encoding="utf-8")))
    deployments = {
        item["metadata"]["name"]: item
        for item in documents
        if item and item.get("kind") == "Deployment"
    }
    services = {}
    for name, deployment in deployments.items():
        if name == "loadgenerator":
            continue  # Fixed requests are issued by the experiment, not the random demo loadgen.
        container = deployment["spec"]["template"]["spec"]["containers"][0]
        environment = {entry["name"]: str(entry.get("value", "")) for entry in container.get("env", [])}
        if name != "redis-cart":
            environment["ENABLE_TRACING"] = "1"
            environment["OTEL_SERVICE_NAME"] = name
            environment["COLLECTOR_SERVICE_ADDR"] = (
                "http://jaeger:4317" if name in {"currencyservice", "paymentservice"} else "jaeger:4317"
            )
        service = {"image": container["image"], "environment": environment}
        if name == "frontend":
            service["ports"] = ["18080:8080"]
        services[name] = service
    services["jaeger"] = {
        "image": "jaegertracing/all-in-one:1.76.0",
        "environment": {"COLLECTOR_OTLP_ENABLED": "true"},
        "ports": ["16686:16686"],
    }
    return {"name": "cia-online-boutique-v2", "services": services}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = generate(args.manifest)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(yaml.safe_dump(result, sort_keys=False), encoding="utf-8")
    print(f"wrote {len(result['services']) - 2} application services, Redis, and Jaeger")


if __name__ == "__main__":
    main()
