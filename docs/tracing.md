# Tracing and metrics

All ten applications export OTLP to `otel-collector:4317`. Node exporters use an
HTTP-prefixed endpoint, Go/Python use host:port, .NET uses its OTLP endpoint, and
adservice uses the pinned OpenTelemetry Java agent. Existing shipping/checkout
Go instrumentation and untrimmed .NET tracing repairs are retained.

The Collector exports traces to Jaeger and generates span metrics. Prometheus
scrapes the connector at port 8889 and platform metrics at port 8000. RED panels
select `SPAN_KIND_SERVER`; client traffic is shown separately. Durations use
milliseconds. The RED queries exclude instrumented gRPC health probes. Error status comes from instrumentation: semantic output changes
can occur without an error span. C01 is a price change, not an availability failure.

The five-step fixed workload is home, product, add cart, view cart and checkout.
Run `python scripts/manage.py demo`. Acceptance requires:

- all ten application service names observed;
- at least fourteen directed cross-service edges;
- nonzero business gRPC client spans and complete client/server pairing;
- no missing parent references;
- every workload HTTP request returns 200 without transport errors.

The query window surrounds the workload, then waits eight seconds for export.
Jaeger queries are deduplicated by trace ID across services. The 1,000 traces per
service query limit is sufficient for the fixed local demo, not a production
ingestion design. Stop unrelated traffic during acceptance. Raw trace JSON and
summary JSON are saved with each collection; API topology is the last collected
window, not a continuously refreshed live graph.

In Jaeger select `frontend`, then a checkout trace. Inspect:

```text
frontend → recommendationservice → productcatalogservice
frontend → checkoutservice → cartservice / currencyservice / paymentservice
                           → shippingservice / emailservice / productcatalogservice
```

Historical Compose results are under
`cia_preexperiment_v2/results/raw/online_boutique_trace_gate` and are only used as
regression fixtures. They are never silently substituted for missing V1 telemetry.
