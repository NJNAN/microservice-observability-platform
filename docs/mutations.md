# Reproducible changes and restoration

`configs/mutations.json` exposes 18 controlled changes and five valid semantic
commit replays. The sixth historical replay candidate R03 was excluded because
the original evaluation found no observable change. A replay applies the documented
file or code hunk, not a claim that the complete historical repository is deployed.

```bash
python -m obsplatform.cli mutation list
python scripts/manage.py mutation --case C01_catalog_price
kubectl --context kind-mop -n mop exec deployment/platform -- python -m obsplatform.cli mutation status
kubectl --context kind-mop -n mop exec deployment/platform -- python -m obsplatform.cli mutation restore C01_catalog_price
```

Use `python scripts/manage.py mutation` for the in-cluster runner: it shares the
same PVC and lock as API requests. A direct host CLI uses host-local data and
requires port-forwarding; do not mix host and in-cluster runners concurrently.

Each run captures original and changed fixed workloads, bounded trace windows,
functional gRPC oracle responses and a final restored trace gate. JSON records
include timestamps, affected service, change type, HTTP statuses, request latency,
trace errors/pairing and changed oracle keys. Orchestration `complete` means the
experiment finished and baseline passed its final gate; it does not mean the
mutation's workload should succeed. Recommendation/order fields may be stochastic;
changed oracle keys are observations, not an accuracy score.

C01 mounts a changed catalog file and should expose a $24.99 sunglasses price
instead of $19.99. C03 misroutes the frontend cart dependency and demonstrates
HTTP failures. Both restore the saved deployment template automatically in
`finally`, including when observation fails. Container file mutations use ConfigMap
subPath mounts and a Pod rollout; source files are never overwritten.

Crash recovery: first verify no runner or API request is still executing. If the
process was killed, remove only `/data/operation.lock` in the platform container
and invoke `mutation restore <case_id>`. Do not delete `/data/active.json`; it is
the recovery record. A mismatched requested case is rejected. A Kubernetes outage
can prevent restoration; restore then remains an explicit outstanding operation.

Export evidence before `make down`:

```bash
kubectl --context kind-mop -n mop exec deployment/platform -- tar czf /tmp/results.tgz -C /data .
kubectl --context kind-mop -n mop cp $(kubectl --context kind-mop -n mop get pod -l app=platform -o jsonpath='{.items[0].metadata.name}'):/tmp/results.tgz ./results.tgz
```
