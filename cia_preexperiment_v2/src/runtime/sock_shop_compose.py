"""Prepare the archived Sock Shop Compose for an isolated tracing gate."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml


def generate(upstream: Path) -> dict:
    original = yaml.safe_load(upstream.read_text(encoding="utf-8"))
    services = original["services"]
    services.pop("user-sim", None)  # A separate deterministic workload is used.
    services["queue-master"].pop("volumes", None)  # Do not mount the Docker socket.
    services["edge-router"]["ports"] = ["18081:80", "18082:8080"]
    for name in ("carts", "orders", "shipping"):
        service = services[name]
        old = service["environment"][0]
        service["environment"] = [old.replace("-Dspring.zipkin.enabled=false", "-Dspring.zipkin.enabled=true -Dspring.zipkin.base-url=http://jaeger:9411 -Dspring.sleuth.sampler.probability=1.0")]
    services["jaeger"] = {
        "image": "jaegertracing/all-in-one:1.76.0",
        "environment": {"COLLECTOR_ZIPKIN_HOST_PORT": ":9411", "COLLECTOR_OTLP_ENABLED": "true"},
        "ports": ["16687:16686"],
    }
    return {"name": "cia-sock-shop-v2", "services": services}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    config = generate(args.upstream)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    print(f"wrote {len(config['services'])} containers including Jaeger")
