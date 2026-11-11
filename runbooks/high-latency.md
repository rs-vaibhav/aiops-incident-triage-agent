# High latency or upstream timeouts

alerts: HighLatency, UpstreamTimeout, SLOLatencyBurn
owner: Application-SRE

## Symptoms
p95/p99 latency above SLO. Clients report timeouts or "deadline exceeded".

## Likely causes
- Slow downstream dependency (database, payment gateway, third-party API)
- CPU throttling because CPU limits are too low
- Insufficient replicas for current traffic

## Diagnosis
- Grafana: compare service latency with dependency latency on the same time range
- `kubectl top pod` and container_cpu_cfs_throttled_seconds_total for throttling
- Check request rate versus the HPA target

## Remediation
1. Identify the slowest dependency from tracing or dependency latency dashboards
2. Scale the deployment out with kubectl scale or raise the HPA maxReplicas
3. Raise CPU limits if the container is being throttled
4. Enable or shorten client timeouts and add retries with backoff for the slow dependency
