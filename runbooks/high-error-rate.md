# High error rate or service down

alerts: HighErrorRate, ServiceDown, SLOErrorBudgetBurn, TargetDown
owner: Application-SRE

## Symptoms
5xx ratio above threshold, error budget burning fast, or Prometheus cannot scrape the target.

## Likely causes
- Bad deployment (code or configuration regression)
- Dependency outage returning errors
- All pods unready so the Service has no endpoints

## Diagnosis
- Check recent deployments: `kubectl rollout history deployment/<name>`
- `kubectl get endpoints <service>` to confirm there are ready endpoints
- Loki: `{app="<name>"} |= "ERROR"` grouped by message

## Remediation
1. Roll back the most recent deployment with kubectl rollout undo if errors started after a release
2. Confirm the Service has ready endpoints and that readiness probes pass
3. Fail over to the secondary region or enable the maintenance page if the outage is customer facing
4. Open a bridge call and notify stakeholders for P1 incidents
