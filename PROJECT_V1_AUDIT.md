# V1 repository audit

Audited 2026-09-27 before implementation. The workspace root has no Git repository;
upstream checkouts are nested inside experiment directories. No research data is deleted or moved.

## Existing

- `cia_preexperiment_v2/data/online-boutique`: Google Online Boutique v0.10.4 release manifests and modified multilingual source.
- `configs/online_boutique_trace_gate.compose.yml` under that directory: ten business services, Redis and Jaeger; existing containers are running separately.
- `src/runtime/online_boutique_trace_gate.py` and `gate_workload.py`: trace audit and five-step shopping journey.
- `results/raw/online_boutique_trace_gate/run_01..03.*`: historical evidence of ten observed application services, fourteen directed edges, 71/71 business gRPC pairs and 5/5 HTTP requests per run.
- `data/mutations/method_controlled/cases.json`: eighteen controlled changes.
- `data/commits/method_replays/cases.json`: six replay candidates; `results/tables/method_experiment/evaluation_status.json` excludes R03 (no observable change), leaving five valid replays and 23 total evaluated cases.
- `src/method/oracle_probe.py`: functional gRPC oracle; `evaluate_cases.py`, `summarize_cases.py`: evaluation scripts.

## Reusable

Official Deployments/Services/probes, fixed workload, Jaeger parent/child analysis, traced source fixes, case files and functional oracle. Preserve their provenance and licenses. Compose remains the development/tracing-debug fallback.

## Needs Refactor

Absolute Windows volume paths, globally named containers, direct Jaeger exporters, local build outputs used as image inputs, missing deployment-independent case runner and API. Historical gate accepted >=10 edges; V1 must enforce >=14 and nonzero complete pairing. Python package will be `obsplatform` to avoid shadowing the standard-library `platform` module.

## Deprecated Research Code

The four preexperiment directories and root research notes remain intact. Hybrid scoring, optimizer experiments and statistical figure generators are not part of the V1 runtime. See `docs/research-history.md` for evidence locations.

## Missing for V1 (at audit time)

kind deployment/bootstrap; Collector; RED metrics; versioned Grafana dashboards; REST API; portable mutation runner and durable restoration; engineering README; CI; current Kubernetes acceptance evidence. Docker is reachable with host permissions, kubectl is installed but no current context exists, kind is absent, and FastAPI is absent from the initial Python environment. Historical numbers are not Kubernetes validation.
