"""Generate portable V1 deployment assets from the preserved upstream manifests."""
import copy
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "cia_preexperiment_v2"


def write(path, content):
    dest = ROOT / path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")


def ywrite(path, obj):
    write(path, yaml.safe_dump(obj, sort_keys=False))


def resources(name, image, ports, args=None, mounts=None, env=None):
    container = {"name": name, "image": image, "ports": [{"containerPort": p} for p in ports],
                 "resources": {"requests": {"cpu": "50m", "memory": "64Mi"},
                               "limits": {"memory": "1Gi"}}}
    if args:
        container["args"] = args
    if env:
        container["env"] = [{"name": k, "value": v} for k, v in env.items()]
    pod = {"containers": [container]}
    if mounts:
        container["volumeMounts"] = [{"name": n, "mountPath": p} for n, p in mounts.items()]
        pod["volumes"] = [{"name": n, "configMap": {"name": n}} for n in mounts]
    return [{"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": name},
             "spec": {"replicas": 1, "selector": {"matchLabels": {"app": name}},
                      "template": {"metadata": {"labels": {"app": name}}, "spec": pod}}},
            {"apiVersion": "v1", "kind": "Service", "metadata": {"name": name},
             "spec": {"selector": {"app": name}, "ports": [
                 {"name": f"p{p}", "port": p, "targetPort": p} for p in ports]}}]


def main():
    base = yaml.safe_load((OLD / "configs/online_boutique_trace_gate.compose.yml").read_text())
    app_names = set(base["services"]) - {"jaeger"}
    images = {}
    patches = {"emailservice": [("email_server.py", "/email_server/email_server.py")],
               "currencyservice": [("server.js", "/usr/src/app/server.js")],
               "paymentservice": [("index.js", "/usr/src/app/index.js")]}
    for service in sorted(app_names):
        entry = base["services"][service]
        if service == "redis-cart":
            images[service] = "redis:7.2-alpine"
        elif service in ("shippingservice", "checkoutservice", "cartservice", "currencyservice", "paymentservice", "emailservice", "adservice"):
            images[service] = f"mop-{service}:v1"
        else:
            images[service] = entry["image"]
        dockerfile = None
        if service in ("currencyservice", "paymentservice"):
            dockerfile = ("FROM node:20-alpine AS deps\nWORKDIR /deps\n"
                          "COPY configs/node-otel/package*.json ./\n"
                          "RUN npm ci --omit=dev --fetch-retries=3\n"
                          f"FROM us-central1-docker.pkg.dev/google-samples/microservices-demo/{service}:v0.10.4\n"
                          "COPY --from=deps /deps/node_modules/ /usr/src/app/node_modules/\n")
        elif service == "emailservice":
            dockerfile = f"FROM {entry['image']}\n"
        elif service == "adservice":
            dockerfile = ("FROM alpine:3.21 AS agent\nRUN wget -q -O /javaagent.jar "
                          "https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/download/v2.31.1/opentelemetry-javaagent.jar\n"
                          "RUN echo 'bbf83c151b6400709e2f225bdd07a04f839d9d13b8b93464241333fd25d3e3ba  /javaagent.jar' | sha256sum -c -\n"
                          f"FROM {entry['image']}\nCOPY --from=agent /javaagent.jar /otel/javaagent.jar\n")
        elif service == "cartservice":
            dockerfile = ("FROM mcr.microsoft.com/dotnet/sdk:9.0 AS build\nWORKDIR /src\n"
                          "COPY cia_preexperiment_v2/data/online-boutique/src/cartservice/src/ .\n"
                          "RUN dotnet publish -c Release -r linux-x64 --self-contained true -p:PublishSingleFile=true -p:PublishTrimmed=false -o /out\n"
                          "FROM us-central1-docker.pkg.dev/google-samples/microservices-demo/cartservice:v0.10.4\n"
                          "COPY --from=build --chown=1000:1000 /out/ /app/\n")
        if dockerfile:
            for source, target in patches.get(service, []):
                dockerfile += f"COPY cia_preexperiment_v2/data/online-boutique/src/{service}/{source} {target}\n"
            write(f"build/{service}.Dockerfile", dockerfile)

    docs = []
    for doc in yaml.safe_load_all((OLD / "data/online-boutique/release/kubernetes-manifests.yaml").read_text()):
        if not doc or doc["metadata"]["name"] not in app_names:
            continue
        name = doc["metadata"]["name"]
        if doc["kind"] == "Deployment":
            pod = doc["spec"]["template"]["spec"]
            container = pod["containers"][0]
            container["image"] = images[name]
            container["imagePullPolicy"] = "IfNotPresent"
            env = copy.deepcopy(base["services"][name].get("environment", {}))
            for k in ("COLLECTOR_SERVICE_ADDR", "OTEL_EXPORTER_OTLP_ENDPOINT"):
                if k in env:
                    env[k] = env[k].replace("jaeger:", "otel-collector:")
            container["env"] = [{"name": k, "value": str(v)} for k, v in env.items()]
            container["resources"] = {"requests": {"cpu": "50m", "memory": "64Mi"}, "limits": {"memory": "768Mi"}}
            if name == "emailservice":
                container["ports"] = [{"containerPort": 5000, "name": "grpc"}]
                for probe in ("readinessProbe", "livenessProbe"):
                    container[probe] = {"tcpSocket": {"port": 5000}, "initialDelaySeconds": 10}
            if name == "adservice":
                container["startupProbe"] = {"tcpSocket": {"port": 9555}, "failureThreshold": 60, "periodSeconds": 5}
        elif doc["kind"] == "Service":
            doc["spec"]["type"] = "ClusterIP"
            if name == "emailservice":
                doc["spec"]["ports"] = [{"name": "grpc", "port": 5000, "targetPort": 5000}]
        docs.append(doc)
    write("k8s/application/application.yaml", "# Derived from Google Online Boutique v0.10.4, Apache-2.0.\n" + yaml.safe_dump_all(docs, sort_keys=False))
    ywrite("k8s/application/kustomization.yaml", {"resources": ["application.yaml"]})
    ywrite("configs/images.yaml", images)
    # Preserve Compose, while providing a portable Collector-based fallback.
    compose = copy.deepcopy(base)
    compose["name"] = "mop-dev"
    for name, entry in compose["services"].items():
        if name == "jaeger":
            entry["ports"] = ["127.0.0.1:16687:16686"]
            continue
        entry["image"] = images[name]
        entry.pop("volumes", None)
        for key in ("COLLECTOR_SERVICE_ADDR", "OTEL_EXPORTER_OTLP_ENDPOINT"):
            if key in entry.get("environment", {}):
                entry["environment"][key] = entry["environment"][key].replace("jaeger:", "otel-collector:")
        if name == "frontend":
            entry["ports"] = ["127.0.0.1:18081:8080"]
    compose["services"]["otel-collector"] = {"image": "otel/opentelemetry-collector-contrib:0.123.0", "command": ["--config=/etc/otel/config.yaml"], "volumes": ["./configs/otel/collector.yaml:/etc/otel/config.yaml:ro"]}
    ywrite("docker-compose.yml", compose)

    cases = []
    for folder, cohort in (("mutations/method_controlled", "controlled"), ("commits/method_replays", "replay")):
        for case in json.loads((OLD / "data" / folder / "cases.json").read_text()):
            if case["case_id"] == "R03_nanos_rounding_076819":
                continue
            row = {k: case[k] for k in ("case_id", "change_type", "changed_service", "description")}
            row["cohort"] = cohort
            row["replay_scope"] = case.get("replay_scope")
            for phase, key in (("original", "override_original"), ("changed", "override" if cohort == "controlled" else "override_changed")):
                original = case.get(key)
                row[phase] = f"cia_preexperiment_v2/data/{folder}/{case['case_id']}/{original.replace(chr(92), '/').split('/')[-1]}" if original else None
            cases.append(row)
    write("configs/mutations.json", json.dumps(cases, indent=2))

    collector = {"receivers": {"otlp": {"protocols": {"grpc": {"endpoint": "0.0.0.0:4317"}, "http": {"endpoint": "0.0.0.0:4318"}}}},
                 "processors": {"batch": {}},
                 "connectors": {"spanmetrics": {"namespace": "traces.span.metrics", "histogram": {"explicit": {"buckets": ["5ms", "10ms", "50ms", "100ms", "500ms", "1s", "5s"]}}, "metrics_flush_interval": "5s"}},
                 "exporters": {"otlp/jaeger": {"endpoint": "jaeger:4317", "tls": {"insecure": True}}, "prometheus": {"endpoint": "0.0.0.0:8889"}},
                 "service": {"pipelines": {"traces": {"receivers": ["otlp"], "processors": ["batch"], "exporters": ["otlp/jaeger", "spanmetrics"]},
                                            "metrics": {"receivers": ["otlp", "spanmetrics"], "exporters": ["prometheus"]}}}}
    ywrite("configs/otel/collector.yaml", collector)
    ywrite("configs/prometheus/prometheus.yaml", {"global": {"scrape_interval": "5s"}, "scrape_configs": [
        {"job_name": "spanmetrics", "static_configs": [{"targets": ["otel-collector:8889"]}]},
        {"job_name": "platform", "static_configs": [{"targets": ["platform:8000"]}]}]})
    ywrite("configs/grafana/datasources.yaml", {"apiVersion": 1, "datasources": [{"name": "Prometheus", "uid": "prometheus", "type": "prometheus", "access": "proxy", "url": "http://prometheus:9090", "isDefault": True}]})
    ywrite("configs/grafana/dashboards.yaml", {"apiVersion": 1, "providers": [{"name": "MOP", "type": "file", "options": {"path": "/var/lib/grafana/dashboards"}}]})
    observability = []
    observability += resources("otel-collector", "otel/opentelemetry-collector-contrib:0.123.0", [4317, 4318, 8889], ["--config=/etc/otel/collector.yaml"], {"otel-config": "/etc/otel"})
    observability += resources("jaeger", "jaegertracing/all-in-one:1.76.0", [4317, 16686], env={"COLLECTOR_OTLP_ENABLED": "true"})
    observability += resources("prometheus", "prom/prometheus:v3.2.1", [9090], ["--config.file=/etc/prometheus/prometheus.yaml", "--storage.tsdb.retention.time=24h"], {"prometheus-config": "/etc/prometheus"})
    observability += resources("grafana", "grafana/grafana:11.6.0", [3000], mounts={"grafana-datasources": "/etc/grafana/provisioning/datasources", "grafana-providers": "/etc/grafana/provisioning/dashboards", "grafana-dashboards": "/var/lib/grafana/dashboards"}, env={"GF_AUTH_ANONYMOUS_ENABLED": "true", "GF_AUTH_ANONYMOUS_ORG_ROLE": "Viewer"})
    write("k8s/observability/stack.yaml", yaml.safe_dump_all(observability, sort_keys=False))
    # ConfigMaps generated here keep kubectl apply -k self-contained.
    for name, files in {"otel-config": ["configs/otel/collector.yaml"], "prometheus-config": ["configs/prometheus/prometheus.yaml"], "grafana-datasources": ["configs/grafana/datasources.yaml"], "grafana-providers": ["configs/grafana/dashboards.yaml"]}.items():
        cm = {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": name}, "data": {Path(f).name: (ROOT / f).read_text() for f in files}}
        ywrite(f"k8s/observability/{name}.yaml", cm)

    dashboards()
    ywrite("k8s/observability/grafana-dashboards.yaml", {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "grafana-dashboards"}, "data": {p.name: p.read_text() for p in sorted((ROOT / "dashboards").glob("*.json"))}})
    ywrite("k8s/observability/kustomization.yaml", {"resources": ["stack.yaml", "otel-config.yaml", "prometheus-config.yaml", "grafana-datasources.yaml", "grafana-providers.yaml", "grafana-dashboards.yaml"]})
    platform = resources("platform", "mop-platform:v1", [8000], env={"MOP_DATA": "/data", "MOP_FRONTEND": "http://frontend:80", "MOP_JAEGER": "http://jaeger:16686", "MOP_ALLOW_MUTATIONS": "1"})
    pod = platform[0]["spec"]["template"]["spec"]
    pod["serviceAccountName"] = "platform"
    pod["volumes"] = [{"name": "data", "persistentVolumeClaim": {"claimName": "platform-data"}}]
    pod["containers"][0]["volumeMounts"] = [{"name": "data", "mountPath": "/data"}]
    pod["containers"][0]["readinessProbe"] = {"httpGet": {"path": "/health", "port": 8000}}
    platform[0]["spec"]["strategy"] = {"type": "Recreate"}
    platform += [{"apiVersion": "v1", "kind": "PersistentVolumeClaim", "metadata": {"name": "platform-data"}, "spec": {"accessModes": ["ReadWriteOnce"], "resources": {"requests": {"storage": "1Gi"}}}},
                 {"apiVersion": "v1", "kind": "ServiceAccount", "metadata": {"name": "platform"}},
                 {"apiVersion": "rbac.authorization.k8s.io/v1", "kind": "Role", "metadata": {"name": "platform"}, "rules": [
                     {"apiGroups": ["apps"], "resources": ["deployments"], "verbs": ["get", "list", "watch", "patch"]},
                     {"apiGroups": [""], "resources": ["configmaps"], "verbs": ["get", "create", "patch"]},
                     {"apiGroups": [""], "resources": ["pods"], "verbs": ["get", "list"]},
                     {"apiGroups": [""], "resources": ["pods/exec"], "verbs": ["create"]}]},
                 {"apiVersion": "rbac.authorization.k8s.io/v1", "kind": "RoleBinding", "metadata": {"name": "platform"}, "subjects": [{"kind": "ServiceAccount", "name": "platform"}], "roleRef": {"apiGroup": "rbac.authorization.k8s.io", "kind": "Role", "name": "platform"}}]
    write("k8s/platform/platform.yaml", yaml.safe_dump_all(platform, sort_keys=False))
    ywrite("k8s/platform/kustomization.yaml", {"resources": ["platform.yaml"]})
    ywrite("k8s/namespace.yaml", {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "mop"}})
    ywrite("k8s/kustomization.yaml", {"namespace": "mop", "resources": ["namespace.yaml", "application", "observability", "platform"]})


def dashboards():
    rate = 'sum by(service_name) (rate(traces_span_metrics_calls_total{span_kind="SPAN_KIND_SERVER",span_name!~".*grpc.health.*"}[2m]))'
    error = 'sum by(service_name) (rate(traces_span_metrics_calls_total{span_kind="SPAN_KIND_SERVER",span_name!~".*grpc.health.*",status_code="STATUS_CODE_ERROR"}[2m]))'
    latency = 'histogram_quantile(0.95, sum by(le,service_name) (rate(traces_span_metrics_duration_milliseconds_bucket{span_kind="SPAN_KIND_SERVER",span_name!~".*grpc.health.*"}[2m])))'
    groups = [("service-overview", "Service Overview", [("Request rate", rate), ("Error rate", error), ("p95 duration (ms)", latency), ("Deployment availability", 'mop_service_ready')]),
              ("distributed-overview", "Distributed System Overview", [("Cross-service client traffic by RPC", 'sum by(service_name,span_name) (rate(traces_span_metrics_calls_total{span_kind="SPAN_KIND_CLIENT",span_name=~".*hipstershop.*"}[2m]))'), ("Slow services (p95 ms)", latency), ("Error services", error)]),
              ("mutation-experiments", "Mutation / Failure Experiment", [("Latest case, change type, affected service, status", 'mop_experiment_info'), ("Workload success ratio", 'mop_workload_success_ratio'), ("Detected HTTP errors", 'mop_detected_errors'), ("Before/after mean duration (ms)", 'mop_workload_duration_ms'), ("Experiment timestamp", 'mop_experiment_timestamp_seconds'), ("Run outcomes", 'mop_mutation_runs')])]
    for uid, title, queries in groups:
        panels = [{"id": i + 1, "type": "timeseries", "title": name, "datasource": {"type": "prometheus", "uid": "prometheus"},
                   "gridPos": {"x": (i % 2) * 12, "y": (i // 2) * 8, "w": 12, "h": 8}, "targets": [{"refId": "A", "expr": query, "legendFormat": "{{service_name}}{{phase}}{{case_id}}{{change_type}}{{service}}{{status}}{{outcome}}"}]} for i, (name, query) in enumerate(queries)]
        doc = {"uid": uid, "title": title, "schemaVersion": 40, "version": 1, "refresh": "5s", "time": {"from": "now-15m", "to": "now"}, "panels": panels,
               "links": [{"title": "Runtime topology JSON", "url": "http://localhost:8000/api/topology", "targetBlank": True}, {"title": "Jaeger traces", "url": "http://localhost:16687", "targetBlank": True}]}
        if uid == "mutation-experiments":
            panels[0]["type"] = "table"
            panels[0]["targets"][0].update(instant=True, format="table")
            panels[4]["type"] = "stat"
            panels[4]["targets"][0]["expr"] = "mop_experiment_timestamp_seconds * 1000"
            panels[4]["fieldConfig"] = {"defaults": {"unit": "dateTimeAsIso"}}
        write(f"dashboards/{uid}.json", json.dumps(doc, indent=2))


if __name__ == "__main__":
    main()
