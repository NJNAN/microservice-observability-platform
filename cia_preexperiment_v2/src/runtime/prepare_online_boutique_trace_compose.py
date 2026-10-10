"""Create the isolated tracing repair Compose from the pinned Online Boutique gate config."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml


def prepare(base: Path, source: Path, agent: Path) -> dict:
    config = yaml.safe_load(base.read_text(encoding="utf-8"))
    services = config["services"]
    for service in ("shippingservice", "checkoutservice", "cartservice", "currencyservice", "paymentservice"):
        services[service]["image"] = f"cia-online-boutique-{service}:trace-gate"

    services["emailservice"]["environment"]["PORT"] = "5000"
    email_source = source / "src/emailservice/email_server.py"
    services["emailservice"]["volumes"] = [
        f"{email_source.resolve().as_posix()}:/email_server/email_server.py:ro"
    ]

    services["adservice"]["volumes"] = [
        f"{agent.resolve().as_posix()}:/otel/javaagent.jar:ro"
    ]
    services["adservice"]["environment"].update({
        "JAVA_TOOL_OPTIONS": "--add-opens=java.base/java.lang=ALL-UNNAMED -javaagent:/otel/javaagent.jar",
        "OTEL_TRACES_EXPORTER": "otlp",
        "OTEL_EXPORTER_OTLP_PROTOCOL": "grpc",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "http://jaeger:4317",
        "OTEL_TRACES_SAMPLER": "always_on",
        "OTEL_METRICS_EXPORTER": "none",
        "OTEL_LOGS_EXPORTER": "none",
    })
    services["cartservice"]["environment"].update({
        "OTEL_EXPORTER_OTLP_ENDPOINT": "http://jaeger:4317",
        "OTEL_EXPORTER_OTLP_PROTOCOL": "grpc",
        "OTEL_DOTNET_EXPERIMENTAL_ASPNETCORE_ENABLE_GRPC_INSTRUMENTATION": "true",
    })
    for service, entrypoint in (("currencyservice", "server.js"), ("paymentservice", "index.js")):
        local = source / "src" / service / entrypoint
        services[service]["volumes"] = [
            f"{local.resolve().as_posix()}:/usr/src/app/{entrypoint}:ro"
        ]
    return config


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--agent", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    for item in (args.base, args.source / "src/emailservice/email_server.py", args.agent):
        if not item.exists():
            parser.error(f"missing input: {item}")
    result = prepare(args.base, args.source, args.agent)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(yaml.safe_dump(result, sort_keys=False), encoding="utf-8")
    print(f"wrote {len(result['services'])} services")


if __name__ == "__main__":
    main()
