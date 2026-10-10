"""Prepare official TeaStore Compose with a pinned local OTel Java agent."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml


def generate(upstream: Path, agent: Path) -> dict:
    original = yaml.safe_load(upstream.read_text(encoding="utf-8"))
    services = original["services"]
    services["db"].pop("ports", None)
    services["webui"]["ports"] = ["18083:8080"]
    for name, service in services.items():
        if name == "db":
            continue
        service["volumes"] = [f"{agent.resolve().as_posix()}:/otel/javaagent.jar:ro"]
        environment = service.setdefault("environment", {})
        environment["JAVA_TOOL_OPTIONS"] = "-javaagent:/otel/javaagent.jar"
        environment["OTEL_SERVICE_NAME"] = name
        environment["OTEL_TRACES_EXPORTER"] = "otlp"
        environment["OTEL_EXPORTER_OTLP_PROTOCOL"] = "grpc"
        environment["OTEL_EXPORTER_OTLP_ENDPOINT"] = "http://jaeger:4317"
        environment["OTEL_TRACES_SAMPLER"] = "always_on"
        environment["OTEL_METRICS_EXPORTER"] = "none"
        environment["OTEL_LOGS_EXPORTER"] = "none"
    services["jaeger"] = {
        "image": "jaegertracing/all-in-one:1.76.0",
        "environment": {"COLLECTOR_OTLP_ENABLED": "true"},
        "ports": ["16688:16686"],
    }
    return {"name": "cia-teastore-v2", "services": services}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--agent", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if not args.agent.is_file():
        parser.error(f"agent file missing: {args.agent}")
    config = generate(args.upstream, args.agent)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    print(f"wrote {len(config['services'])} containers including Jaeger")
