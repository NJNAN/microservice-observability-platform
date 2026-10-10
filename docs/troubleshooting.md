# Troubleshooting demos

Start with scope: did the HTTP request fail, did a downstream RPC fail, or did the
result change while all status codes remained successful? Keep timestamps and the
case ID beside every observation. `make status` shows Pod state; a healthy metrics
scrape alone does not prove application health.

## Demo 1: use service logs

In one terminal run `python scripts/manage.py mutation --case C03_cart_address`.
While its changed phase runs, inspect:

```bash
kubectl --context kind-mop -n mop logs deployment/frontend --since=5m --timestamps
kubectl --context kind-mop -n mop logs deployment/productcatalogservice --since=5m --timestamps
kubectl --context kind-mop -n mop get deployment frontend -o yaml
```

C03 changes `CART_SERVICE_ADDR` to the catalog gRPC port. Correlate cart/checkout
HTTP failures with RPC errors and the wrong dependency address. The process can
remain ready even when business requests fail. The runner subsequently restores
the original address and executes the full acceptance journey.

## Demo 2: inspect an actual request on the network

Open an ephemeral diagnostic container sharing frontend's network namespace:

```bash
kubectl --context kind-mop -n mop debug -it deployment/frontend --image=nicolaka/netshoot:v0.13 --target=server --profile=sysadmin -- tcpdump -i any -nn -c 30 'tcp port 3550 or tcp port 5050'
```

In another terminal, with `make ports` running:

```bash
curl http://127.0.0.1:18081/product/OLJCESPC7Z
```

The capture shows DNS-resolved Pod IP traffic, connection setup and data exchange
to the catalog/checkout ports. Packet traffic establishes that a connection was
attempted; Jaeger and logs establish RPC semantics. These local gRPC calls are
plaintext HTTP/2, but tcpdump packet summaries do not decode protobuf payloads.
The privileged diagnostic profile is for this isolated lab only. If a cluster
disallows ephemeral containers, use its approved capture tooling.

## Demo 3: correlate trace, metric and logs

1. Record the experiment timestamp and case ID from `/api/experiments`.
2. In Grafana's mutation dashboard compare original/changed HTTP failure counts
   and mean request durations. In Service Overview inspect server request/error rate.
3. In Jaeger filter frontend traces within that time window and open the failing
   cart/checkout chain. Match downstream service and RPC name with logs.
4. Check the experiment's `restored` and `baseline_gate_pass`, then repeat the
   shopping journey. Failure to restore is an experiment failure, not a success.

For C01, inspect functional oracle catalog prices; RED error rate may stay zero.
This is expected: successful transport does not prove correct business semantics.

## Common deployment failures

- `ImagePullBackOff`: `kubectl describe pod` reveals the registry error. Check
  Docker proxy/registry access, pull the pinned image on the host and `kind load
  docker-image IMAGE --name mop`. Do not replace it with an unrecorded version.
- Collector crash: inspect `kubectl -n mop logs deployment/otel-collector` using
  the `kind-mop` context. Validate pipeline/connector keys against the pinned version.
- No spans: inspect exporter endpoint and protocol on the affected deployment;
  call `make demo` before expecting metrics or topology.
- Port conflict: stop the old port-forward or pick a different local port.
  Original research Compose uses 18080/16686; V1 uses 18081/16687.
- Docker permission failure: grant the terminal access to Docker Desktop's Linux
  engine. A working docker client binary does not prove engine access.
- Failed restoration: follow `docs/mutations.md`; keep the baseline journal.
