# High CPU or memory usage

alerts: HighCPUUsage, HighMemoryUsage, NodeHighLoad
owner: Infrastructure-Operations

## Symptoms
Node or container CPU above 90 percent for 10 minutes, or memory working set close to the limit.

## Likely causes
- Traffic growth without autoscaling
- Inefficient code path or runaway background job
- Noisy neighbour pod without resource limits on the same node

## Diagnosis
- `kubectl top nodes` and `kubectl top pods -A --sort-by=cpu`
- Grafana node exporter dashboard for the node
- Check for pods without requests/limits: `kubectl get pods -A -o json | jq ...`

## Remediation
1. Identify the top consuming pods with kubectl top pods sorted by cpu or memory
2. Scale out the deployment or enable the Horizontal Pod Autoscaler
3. Set resource requests and limits on pods that have none
4. Cordon the node and reschedule noisy pods if a single node is saturated
