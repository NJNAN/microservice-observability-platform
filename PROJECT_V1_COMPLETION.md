# V1 completion report

Validation date: 2026-09-27. Updated after the evening clean source-build
validation: the last partial acceptance item (full clean rebuild) is now closed.
Implementation and original research evidence are preserved in the shared workspace.
Publication status is recorded separately below; local acceptance measurements
remain dated 2026-09-27.

## Acceptance evidence

| Criterion | Result | Evidence |
| --- | --- | --- |
| kind cluster | PASS | Kubernetes v1.32.2 node Ready |
| Ten application services | PASS | `data/validation/deployments.json` |
| Collector OTLP and Jaeger | PASS | Actual Collector binary configuration validation and kind trace gate |
| Complete distributed trace | PASS after startup | 10 services, 14 directed edges, 71/71 business gRPC pairs |
| Fixed workload | PASS | 5/5 HTTP 200 in stable baseline and restored runs |
| Prometheus | PASS | Ten server-span service labels, real counters and duration histogram |
| Three Grafana dashboards | PASS | API provisioning check, 13 valid PromQL queries, actual browser inspection |
| Runtime topology API | PASS | Live `/api/topology`, nodes/edges/observed RPCs |
| Mutation CLI/API and restore | PASS for tested cases | C01 via CLI; C03 and R04 via REST API |
| C01 functional change | PASS | Catalog price $19.99 -> $24.99; original template restored |
| Clean-build C01 rerun | PASS | All three phases gate 71/71 with 10 services; price $19.99 -> $24.99; restored template matches baseline. First attempt hit a restored-phase cold-start race and is retained (`data/validation/kind-C01-cleanbuild-attempt1.json`); the rerun passed (`kind-C01-cleanbuild.json`) |
| C03 error demo | PASS | Changed workload: one timeout, three HTTP 500, one HTTP 200; restored 5/5 HTTP 200 |
| R04 semantic replay | PASS | Currency conversion outputs differ; restoration and gate pass |
| Source-build Quick Start | PASS | Clean no-cache rebuild of all eight platform images plus the replay image, loaded into kind and deployed; baseline gate and C01 rerun passed on the fresh images (`data/validation/kind-final-gate.json`; `.runtime-nocache-rebuild.log`) |
| CI lint/test/config/build | Local checks PASS; hosted CI PASS (2026-10-10) | Seven tests, Ruff, Kustomize render, Compose/Collector validation, API image build |
| No invented performance results | PASS | No RCA/MTTR/SLO/performance improvement claims |

The first kind gate captured 9 services and 50/71 pairs while currency's exporter
was reconnecting after the Collector became ready. It is retained as startup
failure evidence. A subsequent independent gate and the three restored experiment
gates all pass. Startup and steady-state evidence are not conflated. A similar
cold-start race affected the first restored-phase gate of the clean-build C01 run
(one HTTP 500 and one lost email span); it is retained as
`data/validation/kind-C01-cleanbuild-attempt1.json` and the immediate rerun
passed all three phases.

The earlier image builds initially hit a Node registry ECONNRESET; the source
build uses the preserved npm lockfile, and all npm installs completed in the
final clean rebuild. The clean Docker-only build is no longer a separate pending
step: every image was rebuilt without layer cache, loaded into kind, deployed and
re-validated on 2026-09-27 evening.

## Resume validation

```bash
python scripts/manage.py up
python scripts/manage.py demo
python scripts/manage.py mutation --case C01_catalog_price
python scripts/manage.py ports
# In another terminal:
python scripts/smoke.py
```

V1 Status: PASS (local acceptance; see publication status and Known limitations)

Implemented:
- Official-manifest-based kind deployment, Collector pipeline, Jaeger, Prometheus, Grafana.
- Three versioned dashboards; runtime topology/trace API; durable experiment records.
- CLI list/run/run-all/restore/status and API run/restore; serialized operations and baseline journal.
- Engineering README, architecture/tracing/mutations/troubleshooting docs, CI and curated export tool.
- Clean no-cache source build of every image, validated end to end on kind (build -> load -> deploy -> gates -> mutation). The Docker build context now excludes `.pytest_cache`/`.ruff_cache` (`.dockerignore`, matching `.gitignore`).

Validated:
- Seven Python regression tests, lint and generated configuration checks.
- Platform Docker build and actual Collector configuration validator.
- Collector Compose gate, kind stable-state gate, API/Prometheus/Grafana smoke.
- Clean source rebuild, kind deployment on the fresh image digests, baseline gate, and the C01 mutation with baseline recovery.
- C03 dependency-address failure and R04 semantic commit replay, with baseline recovery.

Current quantitative results:
- Stable kind baseline (clean build): 10/10 services, 14 directed edges, 71/71 gRPC pairs, 5/5 workload success — reproduced on the baseline gate and every C01 phase.
- Catalog: 18 controlled mutations + 5 valid real commit semantic replays.
- Newly exercised on kind: 3/23 distinct cases (C01, C03, R04), with four successful experiment executions because C01 was repeated after the clean build; all restored successfully and passed the restored gate.
- 3 Grafana dashboards, 13 valid PromQL panel queries, 10 services emitting server-span metrics.
- RCA accuracy, MTTR, availability, SLO attainment, telemetry reduction and performance improvement: Not measured yet.

Known limitations:
- Only 3 of 23 distinct catalog cases have been exercised on kind (C01 twice, C03, R04); the rest retain historical Compose evidence only.
- A restored-phase trace gate can hit a cold-start race immediately after a deployment restart (one HTTP 500 and one lost span were captured); a short settle before restored gates would reduce this.
- First-start exporter reconnection, or the first collection window after a long idle, can miss part of a trace window: a post-idle first gate captured 13/14 edges (10/10 services, 5/5 workload, full pairing) and passed on an immediate rerun. Both failures are retained as evidence.
- Hosted CI and publication status are reported in the dated publication record below.
- Single-process local-lab API; no production auth, distributed locking or durable trace/metric backend.
- kind deletion removes experiment PVC; export evidence first. Catalog IDs and time windows are bounded for a lab demo.

V2 priorities:
- Reproduce the clean build on a fresh machine/runner and run all 23 scenarios end to end.
- Add economical PR kind smoke; expand selected trace/dashboard evidence and hosted end-to-end coverage.
- Pin all transitive dependencies and images by digest; improve startup telemetry readiness (including a settle before restored gates).
- Add persistent trace/metric storage and authentication if exposing the platform beyond localhost.

## Publication verification — 2026-10-10

- Target repository: https://github.com/NJNAN/microservice-observability-platform
- Curated release: source code, deployment/configuration, tests, documentation,
  original license notices, and selected validation evidence.
- Fresh release-directory checks: Ruff passed; 7 regression tests passed;
  configuration validation passed (10 apps, 23 cases, 3 dashboards);
  Kustomize rendering and Docker Compose configuration passed.
- Source manifest hashes verified; no credentials found by the release scan.
- Public repository created; anonymous GitHub page access verified: HTTP 200.
- First hosted CI run: [PASS](https://github.com/NJNAN/microservice-observability-platform/actions/runs/38055023817), source commit `153ce29`.
  Linux/Python 3.13 Ruff, 7 regression tests, generated configuration validation,
  Kustomize render, Compose validation, and platform Docker image build passed.
- The manual kind smoke/full-suite jobs were not executed during publication;
  cluster evidence above remains the dated local acceptance evidence.
